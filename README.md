# Task E-2: AI Pipeline Architecture & Cost Optimisation

## The Problem

RapidSales.ai runs an automated sales outreach system for 200 clients. Each client has around 1,000 leads, and the system sends messages over 3 days - WhatsApp on day 1, email on day 2, and an AI voice call on day 3 for people who haven't responded.

Right now, everything uses GPT-4o which is way too expensive. AI costs are eating up 38% of gross revenue. On top of that, voice script generation takes 4.2 seconds which creates awkward delays when calls connect. And there's zero monitoring - the team only finds out about failures when clients complain.

## My Approach

The core insight is that not every message needs the same quality level. WhatsApp messages are short and people skim them on mobile. Emails matter more but 80% of leads aren't high-value. Voice scripts need to sound natural since an AI reads them aloud, but the same script works for leads in the same industry buying the same type of product.

So I redesigned the pipeline to use the right model for each job and cache what makes sense to cache.

## What's In This Submission

**ARCHITECTURE.md** - Explains which model to use for each channel and why. Covers the caching strategy for voice scripts, when to process things async vs sync, and what happens when the LLM fails.

**COST_ANALYSIS.md** - Shows the actual cost calculations using current OpenAI pricing. Breaks down token usage per channel and shows how we get from $2,016/month down to around $370/month.

**OBSERVABILITY.md** - Defines what to log, what metrics to track, and when to alert. Includes a simple 5-metric dashboard for the on-call engineer.

**voice_script_cache.py** - Working Python code for the voice script caching system. Includes the fallback template library and tests.

**diagrams/** - Architecture diagrams in draw.io format showing the pipeline flow and caching logic.

## Results Summary

Monthly AI cost goes from $2,016 to $370, which is an 82% reduction. This drops AI spend from 38% of revenue down to about 7%. Voice script latency improves from 4.2 seconds to around 1 second on average because 75% of requests hit the cache.

## How to Run the Code

You need Python 3.9+ and Redis running locally.

```
pip install redis openai
docker run -d -p 6379:6379 redis:alpine
python voice_script_cache.py test
```

---

Submitted by: _(your name)_
Date: _(submission date)_
