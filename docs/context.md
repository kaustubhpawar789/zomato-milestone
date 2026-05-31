# Project Context: AI-Powered Restaurant Recommendation System

This document captures the full context from `docs/problemStatement.txt` for the Zomato-inspired milestone project.

## Overview

Build an **AI-powered restaurant recommendation service** inspired by Zomato. The system combines **structured restaurant data** with a **Large Language Model (LLM)** to suggest restaurants that match user preferences and explain why each option fits.

## Objective

Design and implement an application that:

1. Accepts user preferences (location, budget, cuisine, ratings, and more)
2. Uses a real-world restaurant dataset
3. Uses an LLM to produce personalized, human-like recommendations
4. Presents clear, useful results to the user

## Data Source

| Item | Detail |
|------|--------|
| **Dataset** | Zomato restaurant data on Hugging Face |
| **URL** | https://huggingface.co/datasets/ManikaSaini/zomato-restaurant-recommendation |
| **Ingestion** | Load and preprocess the dataset |
| **Fields to extract** | Restaurant name, location, cuisine, cost, rating, and other relevant attributes |

## System Workflow

### 1. Data Ingestion

- Load and preprocess the Zomato dataset from Hugging Face
- Extract fields: restaurant name, location, cuisine, cost, rating, etc.

### 2. User Input

Collect preferences from the user:

| Preference | Examples |
|------------|----------|
| **Location** | Delhi, Bangalore |
| **Budget** | low, medium, high |
| **Cuisine** | Italian, Chinese |
| **Minimum rating** | Numeric or threshold |
| **Additional** | family-friendly, quick service, etc. |

### 3. Integration Layer

- Filter and prepare restaurant records that match user input
- Pass structured, filtered results into an LLM prompt
- Design a prompt that helps the LLM **reason** and **rank** options

### 4. Recommendation Engine (LLM)

The LLM should:

- **Rank** restaurants by fit to preferences
- **Explain** why each recommendation matches the user
- **Optionally** summarize the overall set of choices

### 5. Output Display

Present top recommendations in a user-friendly format. Each result should include:

| Field | Description |
|-------|-------------|
| Restaurant Name | Name of the venue |
| Cuisine | Type(s) of food served |
| Rating | User/restaurant rating from data |
| Estimated Cost | Cost indicator from dataset |
| AI-generated explanation | Why this restaurant was recommended |

## Architecture Summary

```
[Hugging Face Dataset]
        ↓
   Data Ingestion & Preprocessing
        ↓
   User Preferences (location, budget, cuisine, rating, extras)
        ↓
   Filter / Prepare Structured Candidates
        ↓
   LLM Prompt (reasoning + ranking)
        ↓
   Top Recommendations + Explanations
        ↓
   User-Facing Display
```

## Key Design Constraints

- **Hybrid approach**: Deterministic filtering on structured data first; LLM for ranking, explanation, and optional summary—not as the sole data source.
- **Explainability**: Every recommendation should include an AI-generated rationale tied to user preferences.
- **Real data**: Recommendations must be grounded in the actual Zomato dataset, not invented restaurants.
- **Usability**: Output must be readable and actionable for end users.

## Success Criteria

- [ ] Dataset loaded and preprocessed from Hugging Face
- [ ] User can specify location, budget, cuisine, minimum rating, and optional preferences
- [ ] System filters candidates before LLM processing
- [ ] LLM ranks options and provides per-restaurant explanations
- [ ] UI or output layer shows name, cuisine, rating, cost, and explanation for top picks

## Reference

- Problem statement source: `docs/problemStatement.txt`
