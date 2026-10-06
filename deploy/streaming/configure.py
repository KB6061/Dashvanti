from pathlib import Path
from datetime import datetime,timezone

root=Path('/home/krishna/food')
import shutil,subprocess
snippet=Path('/etc/nginx/conf.d/dashvanti-gps.inc')
shutil.copyfile(root/'deploy/streaming/nginx-ws.conf',snippet)
snippet.chmod(0o644)
if shutil.which('restorecon'):subprocess.run(['restorecon',str(snippet)],check=True)
env=root/'.env'
content=env.read_text()
values={'GPS_STREAMING_ENABLED':'true','GPS_REDIS_URL':'redis://127.0.0.1:6379/2','GPS_KAFKA_BROKERS':'127.0.0.1:9092','GPS_TTL_SECONDS':'45'}
for key,value in values.items():
    lines=content.splitlines();existing=next((line for line in lines if line.startswith(key+'=')),None)
    if existing and key=='GPS_STREAMING_ENABLED':content=content.replace(existing,key+'='+value)
    elif existing:continue
    else:content+='\n'+key+'='+value+'\n'
env.write_text(content);env.chmod(0o600)
for file in [Path('/etc/nginx/conf.d/dashvanti.conf'),Path('/etc/nginx/conf.d/dashvanti-homepage.conf')]:
    content=file.read_text()
    include='    include /etc/nginx/conf.d/dashvanti-gps.inc;\n'
    content=content.replace('    include /home/krishna/food/deploy/streaming/nginx-ws.conf;\n',include)
    if include in content:
        file.write_text(content);continue
    file.with_suffix('.conf.bak-gps-'+datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')).write_text(content)
    content=content.replace('    location /api/ {',include+'    location /api/ {')
    file.write_text(content)
