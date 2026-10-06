import datetime
import json
import pathlib
import shutil
import subprocess

STATE = pathlib.Path("/var/lib/dashvanti-monitor/status.json")
ENDPOINTS = {
    "streaming": "http://127.0.0.1:8002/health",
    "nginx": "http://127.0.0.1:80/",
    "main": "http://127.0.0.1:8084/",
    "api": "http://127.0.0.1:8001/health",
    "docs": "http://127.0.0.1:8004/health",
    "customer": "http://127.0.0.1:8080/customer/login",
    "restaurant": "http://127.0.0.1:8081/restaurant/login",
    "driver": "http://127.0.0.1:8082/driver/login",
    "admin": "http://127.0.0.1:8083/admin/login",
    "driver-secure": "https://127.0.0.1:8443/driver/login",
}


def main():
    try:
        previous = json.loads(STATE.read_text())
    except (OSError, ValueError):
        previous = {}
    status = {"checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "services": {}, "alerts": []}
    for name, url in ENDPOINTS.items():
        unit = {'streaming':'gps-streaming-service.service','nginx':'nginx.service'}.get(name,f"dashvanti@{name}.service")
        active = subprocess.run(["systemctl", "is-active", "--quiet", unit]).returncode == 0
        headers = ['--header','Host: www.dashvanti.com'] if name == 'nginx' else []
        response = subprocess.run(
            ["curl", "--silent", "--show-error", "--insecure", "--max-time", "8",
             "--output", "/dev/null", "--write-out", "%{http_code}"] + headers + [url],
            capture_output=True, text=True)
        accepted = {'200','301','302','308'} if name == 'nginx' else {'200'}
        healthy = active and response.returncode == 0 and response.stdout in accepted
        failures = 0 if healthy else previous.get("services", {}).get(name, {}).get("failures", 0) + 1
        result = {"healthy": healthy, "http_status": response.stdout,
                  "active": active, "failures": failures, "restarted": False}
        if not healthy:
            status["alerts"].append(f"{name}: failed HTTP/service check ({failures})")
            if failures >= 3:
                restart = subprocess.run(["systemctl", "restart", unit], timeout=30)
                result["restarted"] = restart.returncode == 0
                if result["restarted"]:
                    result["failures"] = 0
        status["services"][name] = result
    disk = shutil.disk_usage("/home/krishna/food")
    status["disk_used_percent"] = round(disk.used / disk.total * 100, 1)
    memory = {}
    for line in pathlib.Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        memory[key] = int(value.split()[0])
    status["memory_used_percent"] = round(
        (1 - memory["MemAvailable"] / memory["MemTotal"]) * 100, 1)
    status["load_average"] = pathlib.Path("/proc/loadavg").read_text().split()[:3]
    if status["disk_used_percent"] >= 90:
        status["alerts"].append("Disk usage exceeds 90%")
    if status["memory_used_percent"] >= 95:
        status["alerts"].append("Memory usage exceeds 95%")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(status, indent=2) + "\n")
    temporary.replace(STATE)
    print(json.dumps(status), flush=True)


if __name__ == "__main__":
    main()
