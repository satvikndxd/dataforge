import io
import zipfile
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from typing import Dict, Any, Optional

from models.schemas import (
    ResearchRequest,
    JobStatus,
    JobResult,
    SourceSelectionRequest,
    DownloadSelectionRequest,
    ImageDownloadRequest,
    AudioDownloadRequest,
    DatasetArchiveRequest,
)
from db import store
from core import research, scraper, nlp_filter, cleaner, deduplicator, dataset_gen

router = APIRouter()


def run_pipeline(job_id: str):
    """Background task to run the complete data forge pipeline."""
    job = store.get_job(job_id)
    if not job:
        return

    try:
        # 1. Searching
        store.update_job(job_id, status="searching", stage="Searching Web", progress=10)
        sources = research.search_topic(job["topic"], num_results=job["num_sources"], modality=job.get("modality", "text"))
        
        # We auto-select all sources initially
        store.update_job(job_id, sources=sources)

        # Pause here. Wait for user to confirm sources
        store.update_job(job_id, status="pending_selection", stage="Awaiting Source Selection", progress=20)
        
    except Exception as e:
        store.update_job(job_id, status="failed", stage="Error", error=str(e))


def continue_pipeline(job_id: str):
    """Continue pipeline after user selects sources."""
    job = store.get_job(job_id)
    if not job:
        return

    try:
        sources_to_scrape = [s for s in job["sources"] if s["url"] in job["selected_urls"]]
        
        # 2. Scraping
        store.update_job(job_id, status="scraping", stage="Scraping Content", progress=30)
        
        def scrape_progress(url, status, progress):
            # Scale 30-60%
            p = 30 + int(progress * 0.3)
            store.update_job(job_id, progress=p, message=f"Scraping: {url} ({status})")
            
        scraped_data = scraper.scrape_urls(sources_to_scrape, progress_callback=scrape_progress, modality=job["modality"])
        
        # Flatten into (url, item) pairs
        raw_items = []
        for url, items in scraped_data.items():
            for item in items:
                raw_items.append((url, item))
                
        # 3. NLP Filtering + Cleaning (60-80%)
        store.update_job(job_id, status="processing", stage="Dispatcher: Assigning Text Processor", progress=60)
        
        if job["modality"] == "text":
            clean_paras = cleaner.clean_paragraphs(raw_items)
            scored_items = nlp_filter.score_paragraphs(clean_paras, job["topic"])
            # 4. Deduplication
            store.update_job(job_id, stage="Text Processor: NLP TF-IDF Check", progress=80)
            final_items = deduplicator.deduplicate(scored_items)
        elif job["modality"] == "audio":
            from core import audio_processor
            store.update_job(job_id, stage="Dispatcher: Assigning Audio Processor", progress=65)
            
            processed_items = []
            def _process_audio_meta(url, item):
                audio_url = item.get("audio_url")
                if audio_url:
                    return audio_processor.process_audio(audio_url, item.get("context_transcript", ""))
                return None
                
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = {executor.submit(_process_audio_meta, url, item): url for url, item in raw_items}
                for future in as_completed(futures):
                    meta = future.result()
                    if meta:
                        processed_items.append(meta)
                    
            store.update_job(job_id, stage="Audio Processor: Deep Speech-to-Text", progress=80)
            
            # Try NLP filter scoring, but do not drop items if STT is weak!
            texts_to_score = [(meta["audio_url"], meta["transcript"]) for meta in processed_items if meta["transcript"].strip()]
            scored = nlp_filter.score_paragraphs(texts_to_score, job["topic"])
            score_map = {u: s for u, t, s in scored} # list of (url, text, score)
            
            final_items = []
            for meta in processed_items:
                score = score_map.get(meta["audio_url"])
                # Fallback to 0.5 because the scraper matched the page conceptually!
                final_score = score if (score is not None and score > 0.0) else 0.5
                final_items.append((meta["audio_url"], meta, final_score))
        elif job["modality"] == "graph_gnn":
            from core import graph_processor
            store.update_job(job_id, stage="Dispatcher: Assigning Graph Processor", progress=70)
            
            # raw_items is list of (url, text_paragraph)
            # We want just the paragraphs to construct the global semantic graph
            texts = [item for _, item in raw_items if isinstance(item, str)]
            
            G = graph_processor.build_graph(texts)
            store.update_job(job_id, stage="Graph Processor: Extracting NER Entities", progress=85)
            
            pr_scores = graph_processor.analyze_graph(G)
            final_items = graph_processor.format_gnn_dataset(G, pr_scores)
        elif job["modality"] == "image_cnn":
            store.update_job(job_id, stage="Image Processor: Cleaning Boilerplate Captions", progress=70)
            clean_images = cleaner.clean_image_captions(raw_items)
            
            store.update_job(job_id, stage="Image Processor: Semantic Graph Tagging", progress=85)
            final_items = nlp_filter.enrich_image_semantics(clean_images, job["topic"])
            
        else:
            # Bypass NLP filter text deduplication for highly structured multimodal data
            # Assume Scraper already did the necessary structuring!
            final_items = [(url, item, 1.0) for url, item in raw_items]
        
        # 5. Result Generation (90-100%)
        store.update_job(job_id, stage="Building Unified Schema Objects", progress=90)
        records = dataset_gen.build_records(final_items, modality=job["modality"])
        
        store.update_job(
            job_id, 
            status="done", 
            stage="Complete", 
            progress=100,
            records=records,
            created_at=records[0]["metadata"]["timestamp"] if records else None
        )

    except Exception as e:
        store.update_job(job_id, status="failed", stage="Error", error=str(e))


@router.post("/research")
async def start_research(req: ResearchRequest, background_tasks: BackgroundTasks):
    job_id = store.create_job(req.topic, req.format, req.num_sources, req.modality)
    background_tasks.add_task(run_pipeline, job_id)
    return {"job_id": job_id}


@router.post("/select_sources")
async def select_sources(req: SourceSelectionRequest, background_tasks: BackgroundTasks):
    job = store.get_job(req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    store.update_job(req.job_id, selected_urls=req.selected_urls)
    background_tasks.add_task(continue_pipeline, req.job_id)
    return {"status": "resumed"}


@router.get("/status/{job_id}", response_model=JobStatus)
async def get_status(job_id: str):
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "stage": job["stage"],
        "progress": job["progress"],
        "message": job.get("message", ""),
        "error": job.get("error")
    }


@router.get("/sources/{job_id}")
async def get_sources(job_id: str):
    """Returns the sources found during 'searching' phase for the user to select."""
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"sources": job.get("sources", [])}


@router.get("/results/{job_id}")
async def get_results(job_id: str):
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="Job not finished")
        
    return {
        "job_id": job["job_id"],
        "topic": job["topic"],
        "modality": job.get("modality", "text"),
        "format": job["format"],
        "sources_used": len(job.get("selected_urls", [])),
        "total_records": len(job.get("records", [])),
        "records": job.get("records", []),
        "created_at": job.get("created_at")
    }


@router.get("/download/{job_id}")
async def download_dataset(job_id: str, selected_ids: str = None):
    """Download dataset. For images/audio, supports optional selected_ids query param (comma-separated)."""
    return await _download_dataset(job_id, selected_ids.split(",") if selected_ids else None)


@router.post("/download/{job_id}")
async def download_dataset_selected(job_id: str, req: DownloadSelectionRequest):
    """Download selected images/audio only."""
    return await _download_dataset(job_id, req.selected_ids)


@router.post("/download_images/{job_id}")
async def download_images_zip(job_id: str, req: ImageDownloadRequest):
    """
    Download preprocessed images as a ZIP file with full control over preprocessing.
    Accepts configuration for target resolution, quality, format, and augmentations.
    """
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="Job not finished")

    if job.get("modality") != "image_cnn":
        raise HTTPException(status_code=400, detail="This endpoint is only for image modality jobs")

    from core import image_processor

    all_records = job.get("records", [])

    # Filter by selected IDs if provided
    if req.selected_ids:
        selected_set = set(req.selected_ids)
        records = [r for r in all_records if r.get("id") in selected_set]
    else:
        records = all_records

    # Parse preprocessing config
    target_size = tuple(req.target_size) if req.target_size else (224, 224)
    quality = req.quality or 95
    output_format = (req.output_format or "JPEG").upper()
    grayscale = req.grayscale or False
    edge_enhance = req.edge_enhance or False
    equalize = req.equalize or False

    ext = "jpg" if output_format == "JPEG" else "png"
    filename_suffix = "_selected" if req.selected_ids else ""

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        # Download and preprocess images concurrently
        def fetch_and_process(idx, record):
            url = record.get("image_url") or record.get("metadata", {}).get("image_url")
            if not url:
                return None
            try:
                r = requests.get(url, timeout=15)
                r.raise_for_status()
                processed = image_processor.resize_and_normalize(
                    r.content,
                    target_size=target_size,
                    quality=quality,
                    output_format=output_format,
                    grayscale=grayscale,
                    edge_enhance=edge_enhance,
                    equalize=equalize,
                )
                return idx, processed, ext
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(fetch_and_process, i, rec): rec for i, rec in enumerate(records)}
            for future in as_completed(futures):
                res = future.result()
                if res:
                    idx, content_bytes, file_ext = res
                    zip_file.writestr(f"images/image_{idx:04d}.{file_ext}", content_bytes)

        # Write preprocessing manifest
        preprocessing_info = image_processor.get_preprocessing_info(
            target_size=target_size,
            quality=quality,
            output_format=output_format,
            grayscale=grayscale,
            edge_enhance=edge_enhance,
            equalize=equalize,
        )
        import json
        zip_file.writestr("preprocessing_config.json", json.dumps(preprocessing_info, indent=2))

        # Add annotations
        ann_fmt = req.annotation_format or "json"
        if ann_fmt == "csv":
            ann_content = dataset_gen.to_csv(records)
            zip_file.writestr("annotations.csv", ann_content)
        else:
            ann_content = dataset_gen.to_json(records)
            zip_file.writestr("annotations.json", ann_content)

    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=dataforge_images_{job_id}{filename_suffix}.zip"}
    )


@router.post("/download_audio/{job_id}")
async def download_audio_zip(job_id: str, req: AudioDownloadRequest):
    """
    Download audio as a ZIP file, with an option to get raw files or generated spectrograms.
    """
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="Job not finished")

    if job.get("modality") != "audio":
        raise HTTPException(status_code=400, detail="This endpoint is only for audio modality jobs")

    from core import audio_processor

    all_records = job.get("records", [])

    if req.selected_ids:
        selected_set = set(req.selected_ids)
        records = [r for r in all_records if r.get("id") in selected_set]
    else:
        records = all_records

    filename_suffix = "_selected" if req.selected_ids else ""
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        def fetch_and_process(idx, record):
            url = record.get("audio_url") or record.get("metadata", {}).get("audio_url")
            if not url:
                return None
            try:
                r = requests.get(url, timeout=15)
                r.raise_for_status()
                
                ext = "mp3"
                if ".wav" in url.lower(): ext = "wav"
                elif ".ogg" in url.lower(): ext = "ogg"
                
                if req.export_format == "spectrogram":
                    processed = audio_processor.generate_spectrogram(r.content, ext)
                    if not processed:
                        return None
                    return idx, processed, "png"
                else:
                    return idx, r.content, ext
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"ZIP fetch failed for {url}: {e}")
                return None

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(fetch_and_process, i, rec): rec for i, rec in enumerate(records)}
            for future in as_completed(futures):
                res = future.result()
                if res:
                    idx, content_bytes, file_ext = res
                    # Put in 'spectrograms' folder if format is spectrogram, else 'audio'
                    folder = "spectrograms" if req.export_format == "spectrogram" else "audio"
                    zip_file.writestr(f"{folder}/audio_{idx:04d}.{file_ext}", content_bytes)

        # Add annotations
        ann_fmt = req.annotation_format or "json"
        if ann_fmt == "csv":
            ann_content = dataset_gen.to_csv(records)
            zip_file.writestr("annotations.csv", ann_content)
        else:
            ann_content = dataset_gen.to_json(records)
            zip_file.writestr("annotations.json", ann_content)

    prefix = "spectrograms" if req.export_format == "spectrogram" else "audio"
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=dataforge_{prefix}_{job_id}{filename_suffix}.zip"}
    )


@router.post("/download_archive/{job_id}")
async def download_text_archive_zip(job_id: str, req: DatasetArchiveRequest):
    """
    Download non-multimedia records (text, graph) packed into a structured ZIP,
    with individual plain text documents and a master configuration JSON/CSV.
    """
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="Job not finished")

    modality = job.get("modality", "text")
    if modality in ["image_cnn", "audio"]:
        raise HTTPException(status_code=400, detail="This endpoint is only for textual/graph modalities")

    all_records = job.get("records", [])

    if req.selected_ids:
        selected_set = set(req.selected_ids)
        records = [r for r in all_records if r.get("id") in selected_set]
    else:
        records = all_records

    filename_suffix = "_selected" if req.selected_ids else ""
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        # Write each document individually
        for idx, record in enumerate(records):
            content_str = record.get("content")
            if not content_str and record.get("type") == "graph_node":
                content_str = json.dumps(record.get("metadata", {}), indent=2)
            if not content_str:
                content_str = "No content."
                
            file_name_doc = f"documents/doc_{idx:04d}.txt"
            zip_file.writestr(file_name_doc, content_str.encode("utf-8"))

        # Add annotations
        ann_fmt = req.annotation_format or "json"
        if ann_fmt == "csv":
            ann_content = dataset_gen.to_csv(records)
            zip_file.writestr("annotations.csv", ann_content)
        else:
            ann_content = dataset_gen.to_json(records)
            zip_file.writestr("annotations.json", ann_content)

    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=dataforge_dataset_{job_id}{filename_suffix}.zip"}
    )




async def _download_dataset(job_id: str, selected_ids: list = None):
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="Job not finished")

    all_records = job.get("records", [])
    
    # Filter by selected IDs if provided
    if selected_ids:
        selected_set = set(selected_ids)
        records = [r for r in all_records if r.get("id") in selected_set]
    else:
        records = all_records
    fmt = job["format"]
    
    modality = job.get("modality")
    if modality in ["image_cnn", "audio"]:
        zip_buffer = io.BytesIO()
        folder_name = "images" if modality == "image_cnn" else "audio"
        filename_suffix = "_selected" if selected_ids else ""

        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            # Helper to fetch individual multimedia bundles
            def fetch_file(idx, record):
                url = record.get("image_url") if modality == "image_cnn" else record.get("audio_url")
                if not url:
                    # Try metadata
                    url = record.get("metadata", {}).get("image_url" if modality == "image_cnn" else "audio_url")
                if not url:
                    return None
                try:
                    r = requests.get(url, timeout=10)
                    r.raise_for_status()
                    ext = "jpg" if modality == "image_cnn" else "mp3"
                    if "png" in url.lower(): ext = "png"
                    elif "webp" in url.lower(): ext = "webp"
                    elif "wav" in url.lower(): ext = "wav"
                    return idx, r.content, ext
                except Exception:
                    return None
                    
            # Download concurrently
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(fetch_file, i, rec): rec for i, rec in enumerate(records)}
                for future in as_completed(futures):
                    res = future.result()
                    if res:
                        idx, content_bytes, ext = res
                        if modality == "image_cnn":
                            from core import image_processor
                            content_bytes = image_processor.resize_and_normalize(content_bytes)
                            ext = "jpg" # Pillow format export standardizes this
                        zip_file.writestr(f"{folder_name}/file_{idx:04d}.{ext}", content_bytes)
                        
            # Add annotations
            if fmt == "csv":
                ann_content = dataset_gen.to_csv(records)
                zip_file.writestr("annotations.csv", ann_content)
            else:
                ann_content = dataset_gen.to_json(records)
                zip_file.writestr("annotations.json", ann_content)
                
        return Response(
            content=zip_buffer.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename=dataforge_{job_id}{filename_suffix}.zip"}
        )

    # Text / Graph / Network datasets
    if fmt == "csv":
        content = dataset_gen.to_csv(records)
        media_type = "text/csv"
        ext = "csv"
    else:
        content = dataset_gen.to_json(records)
        media_type = "application/json"
        ext = "json"
        
    return PlainTextResponse(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename=dataforge_{job_id}.{ext}"}
    )
