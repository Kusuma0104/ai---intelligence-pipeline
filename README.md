# AI Intelligence Pipeline

Production-style AI intelligence data ingestion pipeline for startups, products, research papers, AI jobs, and AI news.

## Overview

This project implements a scalable, fault-tolerant ingestion and enrichment pipeline for AI ecosystem intelligence.

Pipeline:

Sources -> Async Crawlers -> Raw Data -> Normalization -> LLM Extraction -> Entity Resolution -> Storage

## Features

- Async/concurrent crawling using asyncio and aiohttp
- Playwright strategy for JavaScript-rendered pages
- 1000+ startups
- 1000+ products
- 1000 research papers with GitHub metrics
- AI news filtered to the latest 24 hours
- AI jobs filtered to the latest 24 hours
- Full-text extraction and date normalization
- Deterministic entity resolution and canonicalization
- Conservative exact and alias matching
- LLM fallback: Gemini Flash -> Groq Llama -> DeepSeek
- Pydantic schema validation
- 413 payload handling through semantic chunking
- 429 handling with Retry-After and exponential backoff with jitter
- URL/content-hash deduplication
- Raw-source traceability

## Project Structure

src/
  crawler/
    async_crawler.py
    arxiv.py
    browser.py
    complete_github_records.py
    github_metrics.py
    http.py
    jobs.py
    news.py
    paper_github_mapping.py
    products.py
    startups.py
  extraction/
    chunker.py
    classifiers.py
    llm_orchestrator.py
    schemas.py
  resolution/
    entity_resolver.py
  utils/
    dates.py
    logging.py

data/
  startups_1000.csv
  products_1000.csv
  research_papers_1000_verified.csv
  jobs_24h.csv
  news_24h.csv
  entity_mapping_log.csv

architecture.pdf
requirements.txt

## Data Deliverables

- 1000 startups
- 1000 products
- 1000 research papers with GitHub URLs, stars, and publication dates
- AI jobs from 5 distinct sources within the latest 24 hours
- AI news from 5 distinct sources within the latest 24 hours
- Entity mapping log containing raw and canonical entity resolution results

Every record is designed to retain source information for traceability.

## LLM Orchestration

The extraction layer uses:

Gemini Flash -> Groq Llama -> DeepSeek

429 responses use Retry-After and exponential backoff with jitter.

Oversized requests are handled through semantic chunking and progressive reduction to avoid 413 payload errors.

## Entity Resolution

Canonicalization is deterministic and conservative.

1. Normalized exact matching
2. Explicit aliases
3. No uncontrolled fuzzy matching

## Scalability

The crawler uses asynchronous workers, bounded concurrency, queues, retries, and checkpointable processing.

The architecture supports horizontal scaling by increasing workers and partitioning source/entity workloads.

## Freshness and Deduplication

News and jobs are normalized to UTC and filtered against a rolling 24-hour cutoff.

Deduplication uses canonical URLs and source/content hashes where applicable.

## Running

Create and activate a Python virtual environment, install dependencies, configure environment variables, then run modules from the repository root.

Example:

python -m src.crawler.complete_github_records

## Architecture

See architecture.pdf for the complete system architecture covering scalability, fault tolerance, freshness, deduplication, storage, LLM fallback, and browser-rendering strategy.