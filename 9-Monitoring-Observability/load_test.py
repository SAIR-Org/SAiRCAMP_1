#!/usr/bin/env python3
"""
Async load testing for the MLOps API.
"""
import asyncio
import aiohttp
import time
import random
import json
from datetime import datetime

# Configuration
API_URL = "http://localhost:1078/predict"
CONCURRENT_REQUESTS = 10  # Number of simultaneous requests
TOTAL_REQUESTS = 100       # Total requests to send
ERROR_RATE = 0.05          # 5% error rate

# Sample trips
TRIPS = [
    {"tpep_pickup_datetime": "2019-01-15T14:30:00", "PULocationID": 161, "DOLocationID": 237, "passenger_count": 1, "VendorID": 1, "RatecodeID": 1, "trip_distance": 2.5, "payment_type": 1},
    {"tpep_pickup_datetime": "2019-01-15T15:00:00", "PULocationID": 237, "DOLocationID": 170, "passenger_count": 2, "VendorID": 2, "RatecodeID": 1, "trip_distance": 5.2, "payment_type": 1},
    {"tpep_pickup_datetime": "2019-01-15T16:30:00", "PULocationID": 170, "DOLocationID": 161, "passenger_count": 1, "VendorID": 1, "RatecodeID": 2, "trip_distance": 8.7, "payment_type": 2},
    {"tpep_pickup_datetime": "2019-01-15T17:45:00", "PULocationID": 132, "DOLocationID": 237, "passenger_count": 3, "VendorID": 2, "RatecodeID": 1, "trip_distance": 12.3, "payment_type": 1},
]

success = 0
failed = 0
response_times = []

async def send_request(session, request_id):
    """Send a single prediction request."""
    global success, failed
    
    trip = random.choice(TRIPS).copy()
    
    # Randomly inject errors
    if random.random() < ERROR_RATE:
        trip["PULocationID"] = 999  # Invalid zone ID
    
    try:
        start_time = time.time()
        async with session.post(API_URL, json=trip) as response:
            elapsed = (time.time() - start_time) * 1000
            response_times.append(elapsed)
            
            if response.status == 200:
                data = await response.json()
                print(f"✅ [{request_id}] {data.get('predicted_duration_minutes', 'N/A')}min | {elapsed:.0f}ms | v{data.get('model_version', 'N/A')}")
                success += 1
                return {"status": "success", "time": elapsed}
            else:
                print(f"❌ [{request_id}] HTTP {response.status} | {elapsed:.0f}ms")
                failed += 1
                return {"status": "failed", "code": response.status}
    except Exception as e:
        print(f"❌ [{request_id}] Error: {str(e)[:50]}")
        failed += 1
        return {"status": "error", "error": str(e)}

async def run_load_test(concurrent, total):
    """Run the load test with specified concurrency."""
    print("=" * 70)
    print(f"🚀 LOAD TEST: {total} requests with {concurrent} concurrent workers")
    print(f"   Error rate: {ERROR_RATE*100}%")
    print("=" * 70)
    print()
    
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        # Create tasks with semaphore for concurrency control
        semaphore = asyncio.Semaphore(concurrent)
        
        async def limited_request(request_id):
            async with semaphore:
                return await send_request(session, request_id)
        
        # Run all requests
        tasks = [limited_request(i+1) for i in range(total)]
        results = await asyncio.gather(*tasks)
    
    elapsed = time.time() - start_time
    
    # Calculate stats
    avg_time = sum(response_times) / len(response_times) if response_times else 0
    max_time = max(response_times) if response_times else 0
    min_time = min(response_times) if response_times else 0
    
    # Calculate percentiles
    sorted_times = sorted(response_times)
    p50 = sorted_times[int(len(sorted_times) * 0.5)] if sorted_times else 0
    p95 = sorted_times[int(len(sorted_times) * 0.95)] if sorted_times else 0
    p99 = sorted_times[int(len(sorted_times) * 0.99)] if sorted_times else 0
    
    print()
    print("=" * 70)
    print("📊 RESULTS")
    print("=" * 70)
    print(f"  Total Requests:    {total}")
    print(f"  ✅ Success:        {success} ({success/total*100:.1f}%)")
    print(f"  ❌ Failed:         {failed} ({failed/total*100:.1f}%)")
    print(f"  ⏱️  Duration:       {elapsed:.2f}s")
    print(f"  📈 Throughput:     {total/elapsed:.1f} req/s")
    print()
    print("  Response Times:")
    print(f"    Average:         {avg_time:.0f}ms")
    print(f"    Min:             {min_time:.0f}ms")
    print(f"    Max:             {max_time:.0f}ms")
    print(f"    P50:             {p50:.0f}ms")
    print(f"    P95:             {p95:.0f}ms")
    print(f"    P99:             {p99:.0f}ms")
    print("=" * 70)
    
    print("\n📊 Check Grafana: http://localhost:3000/d/mlops-dashboard")
    print("📈 Check Prometheus: http://localhost:9090")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Async load test")
    parser.add_argument("-c", "--concurrent", type=int, default=10, help="Concurrent requests (default: 10)")
    parser.add_argument("-n", "--total", type=int, default=100, help="Total requests (default: 100)")
    parser.add_argument("-e", "--error-rate", type=float, default=0.05, help="Error rate (default: 0.05)")
    
    args = parser.parse_args()
    CONCURRENT_REQUESTS = args.concurrent
    TOTAL_REQUESTS = args.total
    ERROR_RATE = args.error_rate
    
    asyncio.run(run_load_test(CONCURRENT_REQUESTS, TOTAL_REQUESTS))
