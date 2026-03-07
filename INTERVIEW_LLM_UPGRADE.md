# LLM Integration — What We Built & What We're Improving
### (Interview Explanation Guide)

---

## What the Project Does (Current State)

This is an AI-powered fashion recommendation system. A user can upload a photo of a clothing item,
type a description, or do both together — and the system finds visually and contextually similar
products from a database of over 1,500 fashion items scraped from Ajio.

The core technology behind the search is **CLIP** — a model developed by OpenAI that understands
both images and text in the same vector space. So when you upload a photo of a red dress, CLIP
converts that image into a list of numbers (called an embedding). Every product in the database
also has an embedding stored in a **FAISS index** — a fast vector search engine by Meta. The system
finds the products whose embeddings are closest to your query. That's the similarity score you see
on each product card.

The backend is built with **FastAPI**, the database is **PostgreSQL**, and the frontend is
**Next.js with TypeScript**. There's also a **Scrapy-based web scraper** that collects real
product data from Ajio including images, prices, and categories.

---

## The Problem We Identified

The system works well most of the time, but it has one fundamental weakness — **it always returns
results**, even when nothing in the database is a good match.

Think of CLIP + FAISS like a GPS that always gives you directions, even when your destination
doesn't exist. It will route you somewhere nearby, but it's not what you asked for.

For example, if someone searches for "red bridal lehenga" and the database doesn't have one,
CLIP still finds the 20 closest vectors — which might be completely unrelated tops or kurtas.
The user sees irrelevant products with no explanation. This is what we call **hallucination** in
AI systems — confidently giving wrong answers.

---

## The Solution — Integrating LLMs (3 Phases)

To solve this, we're integrating **Claude** (Anthropic's LLM) into the pipeline. Here's what
each phase does in plain language:

---

### Phase 1 — Smarter Search + Filtering Bad Results

**Query Expansion:**
Before sending the user's text query to CLIP, we first pass it through Claude. Claude rewrites
the query into a more detailed, fashion-specific description. For example:

- User types: *"something for a wedding"*
- Claude expands it to: *"elegant ethnic wear, formal occasion, rich fabric, traditional Indian
  style, sherwani or kurta for men"*

This richer description gives CLIP much more to work with, resulting in far more relevant results.

**LLM Re-ranking:**
After CLIP retrieves 50 candidate products, we don't show them all directly. Instead, we send
the original query and each product's title and category to Claude. Claude scores each product's
relevance from 0 to 10 and we only show products scoring 6 or above. Products that scored lower
are shown in a separate "Other possible matches" section so the user still has options but the
best matches are clearly highlighted.

This directly eliminates hallucination — if nothing is relevant, Claude filters everything out
and we show a "No matching products found" message instead of misleading results.

---

### Phase 2 — Claude Vision for Better Image Search

When a user uploads a photo, CLIP converts it to an embedding — but CLIP's image understanding
has limits. It can struggle with backgrounds, lighting, or unusual angles.

In Phase 2, we send the uploaded image to Claude Vision which generates a detailed text
description of what it sees: *"White formal shirt, slim fit, full sleeves, spread collar,
button-down, solid color, light fabric."* We then encode this description with CLIP's text
encoder and combine it with the original image embedding in a weighted average. This hybrid
gives us both the visual similarity from CLIP and the semantic accuracy from Claude Vision,
dramatically improving image search quality.

---

### Phase 3 — AI Fashion Assistant (Chat Mode)

This adds a conversational interface alongside the existing search modes. Instead of using
structured filters, the user just chats naturally:

*"I need something to wear to my friend's sangeet, budget around ₹2000, nothing too heavy."*

Claude understands the occasion, budget, style preference, and implicit category (ethnic wear),
then calls the search API with the right parameters. It shows matching products inside the chat
and explains why each one was picked. The user can then refine: *"I like the second one, show
me more like that but in pink"* — and Claude continues the conversation, remembering context.

This turns the product from a search tool into a personal fashion advisor.

---

## Why This Matters (The Bigger Picture)

The original system is a great demonstration of **multimodal AI** — combining vision and
language models for real-world search. But the limitation was that it was purely retrieval-based
with no intelligence layer on top.

By adding Claude, we're layering **generative AI reasoning** on top of the existing **similarity
search** infrastructure. This is actually how modern AI products are built in industry — a fast
retrieval system (like FAISS or Elasticsearch) combined with an LLM that adds understanding,
filtering, and conversation on top. This pattern is called **RAG — Retrieval Augmented Generation**.

Our system is essentially a fashion-specific RAG application where:
- **Retrieval** = CLIP + FAISS finding candidates
- **Augmentation** = Claude re-ranking, expanding queries, and understanding images
- **Generation** = Claude explaining results and holding conversations

---

## Key Numbers (Current State)

| Metric | Value |
|---|---|
| Products in database | 1,544 |
| Indexed FAISS vectors | 1,542 |
| Embedding dimension | 512 (CLIP ViT-B/32) |
| Average search latency | ~100ms |
| Expected latency after LLM | ~1.5–2.5 seconds |
| Data source | Ajio.com |
| Search modes | Image, Text, Hybrid, AI Chat (Phase 3) |

---

## One-Line Summary for Interviews

*"I built a multimodal fashion recommendation system using CLIP for visual-semantic search and
FAISS for fast retrieval, and I'm upgrading it with Claude LLM to add query understanding,
relevance re-ranking, and a conversational AI shopping assistant — essentially building a
fashion-specific RAG pipeline."*
