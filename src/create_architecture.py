from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

output = "architecture.pdf"

doc = SimpleDocTemplate(
    output,
    pagesize=A4,
    rightMargin=36,
    leftMargin=36,
    topMargin=32,
    bottomMargin=32
)

styles = getSampleStyleSheet()
title = ParagraphStyle(
    "Title2", parent=styles["Title"], alignment=TA_CENTER,
    fontSize=18, leading=22, spaceAfter=12
)
h = ParagraphStyle(
    "Heading2", parent=styles["Heading2"],
    fontSize=12, leading=15, spaceBefore=7, spaceAfter=4
)
body = ParagraphStyle(
    "Body2", parent=styles["BodyText"],
    fontSize=8.5, leading=11, spaceAfter=4
)

story = []

story.append(Paragraph("AI Intelligence Graph – Data Ingestion Architecture", title))
story.append(Paragraph(
    "<b>Goal:</b> Build a scalable, fault-tolerant pipeline for startups, products, "
    "research papers, AI jobs, news and entity-resolution records. The same application "
    "code can scale from 1,000+ records to 500k+ records by increasing infrastructure.",
    body
))

story.append(Paragraph("1. High-Level Architecture", h))
story.append(Paragraph(
    "<b>Sources ? Async Crawlers ? Raw Storage ? Normalization ? LLM Extraction ? "
    "Entity Resolution ? Primary Database ? Vector/Graph Storage ? Google Sheet / API</b>",
    body
))
story.append(Paragraph(
    "Source-specific adapters handle RSS, APIs and web pages. Async workers use bounded "
    "concurrency, timeouts, retries and caching. Raw responses are retained for traceability "
    "and every normalized record keeps its source URL.",
    body
))

story.append(Paragraph("2. Scale Strategy: 1k to 500k+ Records", h))
data = [
    ["Layer", "Scaling approach"],
    ["Crawling", "Async workers + semaphore; partition work by source/entity; horizontal worker scaling."],
    ["Queue", "Use a durable queue such as SQS/Kafka/RabbitMQ to distribute crawl and enrichment jobs."],
    ["Storage", "Object storage for raw HTML/JSON; PostgreSQL for canonical records and metadata."],
    ["Search", "Vector index for semantic retrieval; graph database for entity relationships."],
    ["Deduplication", "Stable source IDs + canonical URLs + content hashes + deterministic entity keys."],
    ["Observability", "Structured logs, metrics, retries, dead-letter queue and per-source health checks."]
]
table = Table(data, colWidths=[80, 420])
table.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
    ("GRID", (0,0), (-1,-1), 0.4, colors.grey),
    ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
    ("FONTSIZE", (0,0), (-1,-1), 7.5),
    ("VALIGN", (0,0), (-1,-1), "TOP"),
    ("LEFTPADDING", (0,0), (-1,-1), 4),
    ("RIGHTPADDING", (0,0), (-1,-1), 4),
    ("TOPPADDING", (0,0), (-1,-1), 4),
    ("BOTTOMPADDING", (0,0), (-1,-1), 4),
]))
story.append(table)

story.append(Paragraph("3. HTTP 429 and 413 Handling", h))
story.append(Paragraph(
    "<b>429 Rate Limit:</b> Retry with exponential backoff and random jitter. "
    "Example delay = min(base × 2^attempt + jitter, maximum delay). Respect Retry-After "
    "when supplied. Use per-source rate limits so one source cannot exhaust worker capacity.",
    body
))
story.append(Paragraph(
    "<b>413 Payload Too Large:</b> Do not repeatedly resend the same payload. Split long "
    "documents into smaller semantic chunks with limited overlap, then process each chunk. "
    "If a provider still rejects a chunk, progressively reduce the chunk size.",
    body
))

story.append(Paragraph("4. Freshness and Distributed Deduplication", h))
story.append(Paragraph(
    "News and jobs are filtered using normalized UTC publication timestamps and a 24-hour "
    "cutoff. When strict dates are unavailable, a documented content/date heuristic may be "
    "used. Distributed workers deduplicate using a deterministic key such as "
    "<b>source + canonical URL</b> and a content hash. Database unique constraints make "
    "writes idempotent even when multiple workers process the same item.",
    body
))

story.append(Paragraph("5. LLM Fallback Chain", h))
story.append(Paragraph(
    "The extraction layer uses a provider fallback chain such as "
    "<b>Gemini Flash ? Groq model ? DeepSeek</b>. Each provider is isolated behind an "
    "adapter. Validation uses Pydantic schemas. A failed provider does not stop the pipeline; "
    "the next provider is attempted. Secrets are stored only in environment variables.",
    body
))

story.append(Paragraph("6. Async Crawler and Difficult Sources", h))
story.append(Paragraph(
    "The crawler uses Python asyncio/aiohttp with bounded concurrency, connection timeouts, "
    "retries and response caching. Playwright Async is available for JavaScript-rendered pages. "
    "For Cloudflare, Datadome or CAPTCHA-protected sources, the system does <b>not</b> bypass "
    "security controls. It uses permitted APIs, official feeds, compliant browser rendering, "
    "rate limiting or a source-specific adapter instead.",
    body
))

story.append(Paragraph("7. Storage Design", h))
story.append(Paragraph(
    "<b>Primary DB:</b> PostgreSQL for canonical entities, source metadata, timestamps, "
    "deduplication keys and audit logs. <b>Vector storage:</b> pgvector or a vector database "
    "for semantic search over descriptions, papers and news. <b>Graph storage:</b> Neo4j or "
    "PostgreSQL graph-compatible structures for Startup–Founder–Product–Paper–Job–News "
    "relationships. Raw source documents remain in object storage.",
    body
))

story.append(Paragraph("8. Fault Tolerance and Traceability", h))
story.append(Paragraph(
    "Failures are isolated per source and per record. Retries use bounded exponential backoff; "
    "permanent failures go to a dead-letter queue for later replay. Checkpoints allow workers "
    "to resume without restarting the full crawl. Every record stores source URL, retrieval time, "
    "normalized date, content hash and processing status, making the dataset auditable and "
    "traceable to its original source.",
    body
))

doc.build(story)
print(f"Created {output}")

