import os
import time
import httpx
import subprocess
import sys

def main():
    print("====================================================")
    print("  EasySDR Target Account — Direct Target E2E Test")
    print("====================================================")

    # 1. Clear database before starting server to ensure clean state
    backend_dir = os.path.abspath(os.path.dirname(__file__))
    test_db = os.path.join(backend_dir, "prospecting_test.db")
    for ext in ["", "-wal", "-shm"]:
        fpath = test_db + ext
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
            except Exception:
                pass
                
    venv_python = os.path.join(backend_dir, "venv", "Scripts", "python.exe")
    print(f"Starting FastAPI backend server using: {venv_python}")
    
    # Run uvicorn on port 8002 to avoid conflicting with active dev server on 8000
    log_file = open("uvicorn_test.log", "w")
    server_process = subprocess.Popen(
        [venv_python, "-m", "uvicorn", "app.main:app", "--port", "8002"],
        cwd=backend_dir,
        stdout=log_file,
        stderr=log_file,
        env={**os.environ, "DATABASE_URL": f"sqlite:///{test_db}"},
        text=True
    )
    
    # Give it a few seconds to boot up and verify connection
    print("Waiting for server to become healthy...")
    healthy = False
    for i in range(15):
        time.sleep(1)
        try:
            res = httpx.get("http://localhost:8002/", timeout=1.0)
            if res.status_code == 200:
                print(f"Server is healthy! Status code: {res.status_code}")
                healthy = True
                break
        except Exception:
            pass
            
    if not healthy:
        print("Error: FastAPI server failed to start.")
        log_file.close()
        sys.exit(1)

    try:
        # 2. Trigger the targeted company registration and run
        print("\nSubmitting a specific company target...")
        # Name includes claims and mga keywords so it scores high fit score (>70) and is qualified for enrichment
        payload = {
            "name": "Target Claims Automation MGA Underwriters",
            "website_or_domain": "https://targetinsurancemga.com/about-us"
        }
        target_res = httpx.post("http://localhost:8002/api/companies/target", json=payload, timeout=15.0)
        print(f"Target response code: {target_res.status_code}")
        if target_res.status_code != 200:
            print(f"Response text: {target_res.text}")
        target_json = target_res.json()
        print(f"Target response json: {target_json}")
        company_id = target_json.get("id")
        domain = target_json.get("domain")

        # 3. Poll status
        print("\nPolling workflow status for manual target...")
        completed = False
        for i in range(60):
            time.sleep(1)
            status_res = httpx.get("http://localhost:8002/api/workflows/status", timeout=15.0)
            jobs = status_res.json()
            if not jobs:
                continue
            
            job_key = list(jobs.keys())[-1]
            job = jobs[job_key]
            print(f"Job Status: {job['status']} | Stage: {job['stage']} | Companies: {job['companies_processed']} | Contacts Synced: {job['contacts_synced']}")
            
            if job['status'] == 'completed':
                completed = True
                break
            elif job['status'] == 'failed':
                print(f"Job failed with status detail: {job}")
                break

        if not completed:
            print("Error: Pipeline run failed or timed out.")
            log_res = httpx.get("http://localhost:8002/api/logs", timeout=15.0)
            print("Latest logs:")
            print(log_res.json())
            sys.exit(1)

        # 4. Fetch metrics
        print("\nFetching system metrics...")
        metrics_res = httpx.get("http://localhost:8002/api/metrics", timeout=15.0)
        metrics = metrics_res.json()
        print("Metrics:")
        print(metrics)
        assert metrics["total_companies"] >= 1

        # 5. Fetch companies
        print("\nFetching target companies...")
        companies_res = httpx.get("http://localhost:8002/api/companies", timeout=15.0)
        companies = companies_res.json()
        print("Discovered Companies:")
        found_target = False
        for co in companies:
            print(f"- {co['name']} ({co['domain']}) | AI Score: {co['ai_score']} | Status: {co['status']}")
            if co["domain"] == "targetinsurancemga.com":
                assert co["status"] == "synced"
                found_target = True
        assert found_target is True

        # 6. Fetch contacts
        print("\nFetching enriched contacts...")
        contacts_res = httpx.get("http://localhost:8002/api/contacts", timeout=15.0)
        contacts = contacts_res.json()
        print("Enriched Contacts:")
        found_contacts = False
        for c in contacts:
            print(f"- {c['name']} ({c['title']}) | Confidence Score: {c['confidence_score']}% | Phone: {c['phone']} | Status: {c['status']}")
            if c["email"] and "@targetinsurancemga.com" in c["email"]:
                assert c["status"] == "synced"
                assert c["confidence_score"] in [80, 90]
                found_contacts = True
        assert found_contacts is True

        print("\n====================================================")
        print("  EasySDR Target Account Prospecting Test PASSED!")
        print("====================================================")

    finally:
        # Terminate server process
        print("\nStopping server...")
        server_process.terminate()
        server_process.wait()
        try:
            log_file.close()
        except Exception:
            pass
        print("Server stopped.")

if __name__ == "__main__":
    main()
