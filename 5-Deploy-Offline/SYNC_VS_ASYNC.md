# Synchronous vs Asynchronous Systems — Mental Model, Concepts & Reference

---

# Part 1 — The Big Idea

Before talking about Online Inference or Batch Inference, we need to understand one of the most fundamental concepts in software engineering:

> **Synchronous vs Asynchronous execution.**

These are **not Machine Learning concepts.**

They apply everywhere:

* Web applications
* Databases
* Operating systems
* Cloud computing
* Distributed systems
* MLOps

One of the biggest misconceptions beginners have is:

```
Online  = Synchronous
Batch   = Asynchronous
```

This is **not true.**

Online/Batch describes **the workload**.

Sync/Async describes **how the client interacts with that workload.**

They answer completely different questions.

---

# Part 2 — The Decision

Imagine a client asks a server to perform some work.

The first question is not:

> "How long will this take?"

The real question is:

> **"Does the client need the answer before it can continue?"**

```
                Client requests work

                        │

          Does the client need the answer now?

               Yes                  No

                │                    │

         Synchronous          Asynchronous
```

This single decision determines the communication pattern.

---

# Part 3 — What Is Synchronous?

A synchronous request means:

> **The client waits until the server finishes.**

Nothing else happens until the response arrives.

```
Client

↓

Send Request

↓

████████ Waiting ████████

↓

Receive Response

↓

Continue
```

The client is blocked.

The connection remains open.

The server performs the work immediately.

When finished, the server returns the result.

Only then can the client continue.

---

## Restaurant Example

Imagine ordering food.

```
Walk to counter

↓

Order food

↓

Stand there waiting

↓

Food is ready

↓

Leave
```

You cannot leave the restaurant without your food.

You are blocked until the work finishes.

This is synchronous communication.

---

## Why Synchronous Exists

The important point is **not speed**.

Some synchronous requests finish in 5 milliseconds.

Others may take several seconds.

The real reason synchronous systems exist is:

> **The caller cannot continue without the result.**

For example:

### Uber

```
Request fare

↓

Need price

↓

Cannot book ride

↓

Must wait
```

---

### Credit Card Payment

```
Purchase

↓

Fraud Detection

↓

Approve?

↓

Continue
```

The payment cannot continue until the fraud model answers.

---

### ChatGPT

```
Generate Token #1

↓

Need Token #1

↓

Generate Token #2

↓

Need Token #2

↓

Generate Token #3
```

Each token depends on the previous one.

The generation process is inherently synchronous.

---

# Part 4 — What Is Asynchronous?

Asynchronous execution means:

> **The client does not wait for the work to finish.**

Instead:

```
Client

↓

Request Work

↓

Server accepts request

↓

Immediate acknowledgement

↓

Client continues working

↓

Server finishes later

↓

Result becomes available
```

The client is never blocked.

---

## Restaurant Example

Instead of waiting:

```
Order food

↓

Receive ticket

↓

Go shopping

↓

Restaurant finishes cooking

↓

Notification

↓

Collect food
```

You continue your day.

The restaurant works independently.

---

## Why Asynchronous Exists

Many people think asynchronous systems exist because something is slow.

That is only partially true.

The deeper reason is:

> **The caller does not need the answer immediately.**

Examples:

* Sending emails
* Video encoding
* Report generation
* Data processing
* Batch ML inference

Even if a task only takes one second, it can still be asynchronous if nobody needs the answer immediately.

---

# Part 5 — Comparing the Two

| Synchronous                  | Asynchronous                                    |
| ---------------------------- | ----------------------------------------------- |
| Client waits                 | Client continues immediately                    |
| Connection stays open        | Connection closes immediately                   |
| Response contains the result | Response confirms work started                  |
| Simple request-response      | Usually job-based                               |
| No polling required          | Polling, callbacks, or notifications are common |

---

# Part 6 — Online vs Batch Is A Different Dimension

This is where many engineers become confused.

Online vs Batch is **NOT** the same as Sync vs Async.

Instead:

```
Question 1

What workload are we solving?

↓

Online
or
Batch


Question 2

How should clients communicate?

↓

Synchronous
or
Asynchronous
```

These are independent decisions.

---

## Example Matrix

| Workload | Synchronous                                  | Asynchronous                      |
| -------- | -------------------------------------------- | --------------------------------- |
| Online   | ✅ Real-time prediction API                   | ✅ Upload image and notify later   |
| Batch    | ✅ Python script processing one month of data | ✅ Batch scoring API (this course) |

This means:

```
Online ≠ Synchronous

Batch ≠ Asynchronous
```

They are simply the most common combinations.

---

# Part 7 — Module 4: Online + Synchronous

In the previous module we built this API:

```
POST /predict

↓

Load Model

↓

Preprocess

↓

Predict

↓

Return Prediction
```

The entire inference happens inside one HTTP request.

```
Client

POST /predict

↓

FastAPI

↓

Model Inference

↓

Prediction

↓

HTTP Response
```

The client waits.

Everything happens before the response is returned.

This is synchronous communication.

---

# Part 8 — Module 5: Batch + Asynchronous

Now consider batch scoring.

Instead of predicting one trip,

we score an entire month.

```
April 2020

↓

204,000 taxi trips

↓

Preprocess

↓

Run inference

↓

Store predictions

↓

Compute metrics

↓

Save results
```

This takes approximately two minutes.

More importantly,

**nobody needs the answer immediately.**

So instead of waiting...

```
POST /score

↓

Start Job

↓

Return immediately

↓

Score in background

↓

Store results

↓

Client checks later
```

This is asynchronous communication.

---

# Part 9 — Understanding Our FastAPI Code

Our implementation uses FastAPI's `BackgroundTasks`.

The important line is:

```python
background_tasks.add_task(
    _run_score_job,
    year,
    month
)
```

Notice what does **NOT** happen.

We are **not** calling:

```python
_run_score_job(year, month)
```

That would execute immediately.

Instead,

we register a background task.

FastAPI responds to the client first.

Only after the response is sent does the background work begin.

---

## Timeline

```
Client

POST /score

↓

FastAPI receives request

↓

Register background task

↓

HTTP Response

{
    "status": "started"
}

────────────────────────────

Background thread begins

↓

Load Champion Model

↓

Download Data

↓

Preprocess

↓

Predict

↓

Save Parquet

↓

Save SQLite Result

↓

Job Finished
```

Notice something important.

The HTTP request has already completed.

The server continues working after the client disconnects.

That is the essence of asynchronous execution.

---

# Part 10 — Why Polling Exists

Since the response returns immediately,

the client needs another way to know when the work finishes.

Our API exposes:

```
GET /running
```

to see active jobs.

```
GET /results/{year}/{month}
```

to retrieve completed results.

Typical workflow:

```
POST /score

↓

{
    "status": "started"
}

↓

Client continues working

↓

GET /running

↓

Still running?

↓

GET /results/2020/04

↓

Finished
```

The client asks later instead of waiting.

This technique is called **polling**.

---

# Part 11 — Background Tasks Are Not Production Job Systems

FastAPI BackgroundTasks are an excellent teaching tool.

They help us understand asynchronous execution without introducing additional infrastructure.

However,

large production systems rarely execute long-running jobs this way.

Instead they usually separate responsibilities.

```
Client

↓

API Server

↓

Message Queue

↓

Worker Process

↓

Database / Object Storage
```

The API accepts requests.

Workers perform computation.

Queues distribute jobs.

This architecture allows:

* Multiple workers
* Automatic retries
* Horizontal scaling
* Persistent job queues
* Fault tolerance

Our course intentionally simplifies this using BackgroundTasks so students can focus on the execution model before learning distributed systems.

---

# Part 12 — Connecting Everything Together

At this point we have built two deployment patterns.

## Module 4

```
Workload

Online Inference

Communication

Synchronous

Flow

Client

↓

POST /predict

↓

Inference

↓

Prediction

↓

Response
```

---

## Module 5

```
Workload

Batch Inference

Communication

Asynchronous

Flow

Client

↓

POST /score

↓

Job Started

↓

Background Processing

↓

Predictions Saved

↓

Metrics Saved

↓

GET /results
```

Same machine learning model.

Same preprocessing.

Same MLflow registry.

Completely different execution strategy.

---

# Quick Reference

## Synchronous

```
Client

↓

Request

↓

Wait

↓

Response

↓

Continue
```

**Use when:**

* The client cannot continue without the answer.
* Low latency is required.
* Immediate decisions are needed.

Examples:

* Online prediction
* Authentication
* Fraud detection
* Recommendation APIs
* Chat completion

---

## Asynchronous

```
Client

↓

Request

↓

Job Accepted

↓

Continue Working

↓

Server Finishes Later

↓

Retrieve Result
```

**Use when:**

* The client does not need the answer immediately.
* Processing is long-running.
* Large workloads are involved.
* Results can be consumed later.

Examples:

* Batch ML scoring
* Report generation
* Video transcoding
* Email delivery
* Data processing pipelines

---

# Final Mental Model

```
Question 1

What workload am I solving?

↓

Online
or
Batch


Question 2

How should clients communicate?

↓

Synchronous
or
Asynchronous
```

These are two independent architectural decisions.

Understanding this distinction is fundamental to building production Machine Learning systems.
