#!/usr/bin/env python3
"""
Test script to demonstrate MorphCloud abuild SSH issues.

Usage:
    python test_abuild_ssh.py --concurrent 10 --builds 20 --step-duration 60
    python test_abuild_ssh.py --concurrent 5 --builds 10 --large-output  # Generate large stdout
"""

import argparse
import asyncio
import os
import time
from datetime import datetime

from dotenv import load_dotenv
from morphcloud.api import MorphCloudClient
from paramiko.ssh_exception import SSHException, ChannelException

load_dotenv()
MORPH_API_KEY = os.environ["MORPH_API_KEY"]

# Global tracking
_concurrent_builds = 0
_concurrent_builds_lock = asyncio.Lock()
_results = []
_results_lock = asyncio.Lock()


async def run_single_build(
    mc: MorphCloudClient,
    build_id: int,
    step_duration: int,
    large_output: bool,
) -> dict:
    """Run a single abuild with sleep steps."""
    global _concurrent_builds

    result = {
        "build_id": build_id,
        "status": "unknown",
        "duration": 0,
        "concurrent_at_start": 0,
        "concurrent_at_failure": 0,
        "error": None,
    }

    start_time = time.time()

    try:
        # Track concurrent builds
        async with _concurrent_builds_lock:
            _concurrent_builds += 1
            result["concurrent_at_start"] = _concurrent_builds

        print(f"[Build {build_id}] Starting (concurrent: {result['concurrent_at_start']})")

        # Create snapshot
        snap = await mc.snapshots.acreate(
            vcpus=2,
            memory=4096,
            disk_size=5000,
            digest="test-abuild-ssh",  # Cache base image
        )

        # Define steps - either simple or with large output
        if large_output:
            # Generate ~10MB of output to fill SSH buffer
            output_cmd = 'for i in $(seq 1 100000); do echo "Line $i: $(date) - padding padding padding padding"; done'
            steps = [
                f'echo "Build {build_id} Step 1 starting" && sleep {step_duration} && {output_cmd}',
                f'echo "Build {build_id} Step 2 starting" && sleep {step_duration} && {output_cmd}',
                f'echo "Build {build_id} Step 3 starting" && sleep {step_duration} && echo "Done"',
            ]
        else:
            steps = [
                f'echo "Build {build_id} Step 1 starting" && sleep {step_duration} && echo "Step 1 done"',
                f'echo "Build {build_id} Step 2 starting" && sleep {step_duration} && echo "Step 2 done"',
                f'echo "Build {build_id} Step 3 starting" && sleep {step_duration} && echo "Step 3 done"',
            ]

        build_result = await snap.abuild(steps=steps)
        duration = time.time() - start_time

        result["status"] = "success"
        result["duration"] = duration
        result["snapshot_id"] = build_result.id
        print(f"[Build {build_id}] SUCCESS in {duration:.1f}s")

    except ChannelException as e:
        duration = time.time() - start_time
        async with _concurrent_builds_lock:
            result["concurrent_at_failure"] = _concurrent_builds
        result["status"] = "channel_exception"
        result["duration"] = duration
        result["error"] = f"ChannelException({e.args[0] if e.args else '?'}, '{e.args[1] if len(e.args) > 1 else '?'}')"
        print(f"[Build {build_id}] CHANNEL_EXCEPTION after {duration:.1f}s (concurrent: {result['concurrent_at_failure']}): {result['error']}")

    except SSHException as e:
        duration = time.time() - start_time
        async with _concurrent_builds_lock:
            result["concurrent_at_failure"] = _concurrent_builds
        result["status"] = "ssh_exception"
        result["duration"] = duration
        result["error"] = f"{type(e).__name__}: {str(e)}"
        print(f"[Build {build_id}] SSH_EXCEPTION after {duration:.1f}s (concurrent: {result['concurrent_at_failure']}): {result['error']}")

    except Exception as e:
        duration = time.time() - start_time
        async with _concurrent_builds_lock:
            result["concurrent_at_failure"] = _concurrent_builds
        result["status"] = "error"
        result["duration"] = duration
        result["error"] = f"{type(e).__name__}: {str(e)}"
        print(f"[Build {build_id}] ERROR after {duration:.1f}s: {result['error']}")

    finally:
        async with _concurrent_builds_lock:
            _concurrent_builds -= 1
        async with _results_lock:
            _results.append(result)

    return result


async def main(concurrent: int, total_builds: int, step_duration: int, large_output: bool):
    """Run multiple concurrent abuild tests."""
    print(f"\n{'='*60}")
    print("MorphCloud abuild SSH Test")
    print(f"{'='*60}")
    print(f"Concurrent builds: {concurrent}")
    print(f"Total builds: {total_builds}")
    print(f"Step duration: {step_duration}s")
    print(f"Large output: {large_output}")
    print(f"Started at: {datetime.now().isoformat()}")
    print(f"{'='*60}\n")

    mc = MorphCloudClient(api_key=MORPH_API_KEY)
    semaphore = asyncio.Semaphore(concurrent)

    async def run_with_limit(build_id: int):
        async with semaphore:
            return await run_single_build(mc, build_id, step_duration, large_output)

    tasks = [run_with_limit(i) for i in range(total_builds)]
    await asyncio.gather(*tasks, return_exceptions=True)

    # Print summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")

    success = [r for r in _results if r["status"] == "success"]
    channel_exc = [r for r in _results if r["status"] == "channel_exception"]
    ssh_exc = [r for r in _results if r["status"] == "ssh_exception"]
    errors = [r for r in _results if r["status"] == "error"]

    print(f"Success: {len(success)}/{total_builds}")
    print(f"ChannelException: {len(channel_exc)}/{total_builds}")
    print(f"SSHException: {len(ssh_exc)}/{total_builds}")
    print(f"Other errors: {len(errors)}/{total_builds}")

    if channel_exc:
        print("\nChannelException details:")
        for r in channel_exc:
            print(f"  Build {r['build_id']}: after {r['duration']:.1f}s, concurrent={r['concurrent_at_failure']}, {r['error']}")

    if ssh_exc:
        print("\nSSHException details:")
        for r in ssh_exc:
            print(f"  Build {r['build_id']}: after {r['duration']:.1f}s, concurrent={r['concurrent_at_failure']}, {r['error']}")

    if errors:
        print("\nOther error details:")
        for r in errors:
            print(f"  Build {r['build_id']}: after {r['duration']:.1f}s, {r['error']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test MorphCloud abuild SSH issues")
    parser.add_argument("--concurrent", type=int, default=5, help="Number of concurrent builds")
    parser.add_argument("--builds", type=int, default=10, help="Total number of builds to run")
    parser.add_argument("--step-duration", type=int, default=30, help="Sleep duration per step (seconds)")
    parser.add_argument("--large-output", action="store_true", help="Generate large stdout to trigger buffer issues")

    args = parser.parse_args()
    asyncio.run(main(args.concurrent, args.builds, args.step_duration, args.large_output))
