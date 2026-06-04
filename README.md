# DISASTER

Kubernetes/k3s 기반 재난 상황 이미지 제보 실시간 분산 분석 시스템입니다. 목표는 AI 정확도 경쟁이 아니라, 재난 상황처럼 이미지 분석 요청이 급증할 때 RabbitMQ 기반 비동기 처리와 Worker scale-out으로 큐 대기열과 처리 지연이 줄어드는 모습을 보여주는 것입니다.

## 1. Windows PowerShell에서 빈 GitHub 레포 clone

```powershell
cd D:\2_Konkuk\Project\Python\2026_4_1\DSC
git clone https://github.com/2601-DSC-4/DISASTER.git DISASTER
cd DISASTER
```

현재 원격 레포가 비어 있으면 `warning: You appear to have cloned an empty repository.` 메시지가 나올 수 있습니다. 정상입니다.

## 2. 전체 구조

```text
DISASTER/
  docker-compose.yml
  backend/       FastAPI API 서버
  worker/        이미지 분석 Worker
  aggregator/    분석 결과 Redis 저장기
  simulator/     이미지 업로드 부하 생성기
  dashboard/     React Dashboard
  k8s/           k3s/Kubernetes 매니페스트
  sample_images/ 테스트용 업로드 이미지
  storage/       업로드 이미지 저장 폴더
```

## 3. Docker Desktop 설치 후 Docker Compose 실행

Windows에서는 Docker Desktop을 설치하고 실행한 뒤 PowerShell에서 다음 명령을 사용합니다.

```powershell
cd D:\2_Konkuk\Project\Python\2026_4_1\DSC\DISASTER
docker compose up --build
```

백그라운드 실행:

```powershell
docker compose up --build -d
```

로그 확인:

```powershell
docker compose logs -f
```

종료:

```powershell
docker compose down
```

## 4. 접속 URL

- RabbitMQ 관리 페이지: http://localhost:15672
- RabbitMQ 계정: Docker Compose는 `guest / guest`, k3s는 `disaster / disasterpass`
- FastAPI 문서: http://localhost:8000/docs
- Dashboard: http://localhost:3000

## 5. 평상시 시뮬레이션 실행

기본 `normal` 모드는 1초당 1장 업로드합니다.

```powershell
docker compose run --rm -e MODE=normal -e RATE=1 -e DURATION=30 simulator
```

## 6. 재난 상황 시뮬레이션 실행

`disaster` 모드는 기본적으로 1초당 20장 업로드합니다.

```powershell
docker compose run --rm -e MODE=disaster -e RATE=20 -e DURATION=30 simulator
```

Dashboard의 현재 큐 길이와 평균 처리 시간을 보거나, RabbitMQ 관리 페이지에서 `image.task.queue` 메시지 수를 확인합니다.

## 7. Docker Compose에서 Worker scale-out

처음에는 Worker 1개로 실행합니다.

```powershell
docker compose up --build -d --scale worker=1
```

재난 상황 시뮬레이션 중 Worker를 5개로 늘립니다.

```powershell
docker compose up -d --scale worker=5
```

다시 1개로 줄이기:

```powershell
docker compose up -d --scale worker=1
```

## 8. API 요약

이미지 제보 업로드:

```powershell
curl.exe -X POST http://localhost:8000/reports `
  -F "image=@sample_images/flood_001.jpg" `
  -F "location=서울시 동대문구" `
  -F "description=도로가 침수되었습니다."
```

최근 분석 결과:

```powershell
curl.exe http://localhost:8000/reports/recent
```

통계:

```powershell
curl.exe http://localhost:8000/stats/summary
```

큐 길이:

```powershell
curl.exe http://localhost:8000/queue/status
```

## 9. Mock 분석 규칙

중간발표 단계에서는 실제 AI 모델 대신 파일명 기반 Mock 분석기를 사용합니다.

| 파일명 포함 문자열 | category | riskLevel |
| --- | --- | --- |
| `fire` | `FIRE` | `HIGH` |
| `flood` | `FLOOD` | `HIGH` |
| `smoke` | `FIRE` | `MEDIUM` |
| `normal` | `NORMAL` | `LOW` |
| 그 외 | `UNKNOWN` | `LOW` |

Worker는 각 작업마다 `time.sleep(0.3)`을 수행하여 분석 시간이 걸리는 상황을 만듭니다.

## 10. k3s, KEDA 설치 후 k8s 매니페스트 배포

Ubuntu 미니PC 또는 Linux 환경에서 k3s를 설치합니다.

```bash
curl -sfL https://get.k3s.io | sh -
sudo kubectl get nodes
```

KEDA는 RabbitMQ queue length를 보고 `analysis-worker` Deployment를 자동 확장합니다. Helm 설치 후 다음 스크립트를 실행합니다.

```bash
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
bash scripts/install-keda.sh
```

이미지를 로컬에서 빌드합니다.

```bash
docker compose build
```

k3s는 Docker가 아니라 containerd를 사용하므로, 로컬 Docker 이미지를 k3s로 가져와야 합니다.

```bash
docker save disaster-backend:latest disaster-worker:latest disaster-aggregator:latest disaster-simulator:latest disaster-dashboard:latest -o disaster-images.tar
sudo k3s ctr images import disaster-images.tar
```

기본 앱과 KEDA `ScaledObject`를 배포합니다.

```bash
kubectl apply -k k8s
kubectl get pods -n disaster-system
kubectl get scaledobject -n disaster-system
```

접속:

- Dashboard: `http://<미니PC_IP>:30000`
- FastAPI: `http://<미니PC_IP>:30080/docs`
- RabbitMQ 관리 페이지: `http://<미니PC_IP>:31672`

삭제:

```bash
kubectl delete -k k8s
```

## 11. k3s에서 KEDA Worker 자동 scale-out

최종발표 핵심은 수동 `kubectl scale`이 아니라 KEDA 자동 확장입니다. `k8s/keda-scaledobject.yaml`은 `image.task.queue` 길이를 기준으로 `analysis-worker`를 1개에서 최대 5개까지 조절합니다.

```bash
kubectl get pods -n disaster-system -w
kubectl get hpa -n disaster-system
kubectl describe scaledobject analysis-worker-rabbitmq-scaler -n disaster-system
```

## 12. k3s에서 Simulator Job 실행

평상시 normal mode는 1초당 1장 업로드합니다.

```bash
kubectl delete job upload-simulator-normal -n disaster-system --ignore-not-found
kubectl apply -f k8s/jobs/normal-simulator-job.yaml
kubectl logs -f job/upload-simulator-normal -n disaster-system
```

재난 disaster mode는 1초당 20장 업로드합니다.

```bash
kubectl delete job upload-simulator-disaster -n disaster-system --ignore-not-found
kubectl apply -f k8s/jobs/disaster-simulator-job.yaml
kubectl logs -f job/upload-simulator-disaster -n disaster-system
```

## 13. 미니PC Ubuntu에서 GitHub clone 후 k3s 실행

```bash
sudo apt update
sudo apt install -y git docker.io
sudo systemctl enable --now docker

cd ~
git clone https://github.com/2601-DSC-4/DISASTER.git
cd DISASTER

curl -sfL https://get.k3s.io | sh -
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
bash scripts/install-keda.sh

docker compose build
docker save disaster-backend:latest disaster-worker:latest disaster-aggregator:latest disaster-simulator:latest disaster-dashboard:latest -o disaster-images.tar
sudo k3s ctr images import disaster-images.tar

kubectl apply -k k8s
kubectl get pods -n disaster-system
```

## 14. 중간발표 데모 순서

1. `docker compose up --build -d --scale worker=1`
2. Dashboard, FastAPI docs, RabbitMQ 관리 페이지를 연다.
3. 평상시 시뮬레이션 실행:

   ```powershell
   docker compose run --rm -e MODE=normal -e RATE=1 -e DURATION=30 simulator
   ```

4. 큐가 거의 쌓이지 않는 것을 Dashboard 또는 RabbitMQ에서 확인한다.
5. 재난 상황 시뮬레이션 실행:

   ```powershell
   docker compose run --rm -e MODE=disaster -e RATE=20 -e DURATION=30 simulator
   ```

6. Worker 1개에서는 `image.task.queue`가 쌓이는 것을 확인한다.
7. Worker를 5개로 늘린다.

   ```powershell
   docker compose up -d --scale worker=5
   ```

8. 큐 길이와 평균 처리 시간이 줄어드는 것을 확인한다.

## 15. 최종발표 데모 순서

1. 미니PC Ubuntu 또는 로컬 Linux 환경에서 k3s를 실행한다.
2. `bash scripts/install-keda.sh`로 KEDA를 설치한다.
3. `kubectl apply -k k8s`로 RabbitMQ, Redis, backend, worker, aggregator, dashboard, KEDA ScaledObject를 배포한다.
4. `kubectl get pods -n disaster-system`으로 전체 Pod 상태를 확인한다.
5. normal mode Job을 실행하고 큐가 거의 쌓이지 않는 것을 확인한다.
6. disaster mode Job을 실행하고 RabbitMQ 관리 페이지 또는 Dashboard에서 큐 길이 증가를 확인한다.
7. `kubectl get pods -n disaster-system -w`로 KEDA가 Worker Pod를 자동 증가시키는 것을 확인한다.
8. Worker 증가 후 큐 길이가 감소하고, 부하가 끝나면 Worker가 다시 1개로 줄어드는 것을 확인한다.

자세한 발표 흐름은 `docs/final-demo-scenario.md`를 참고합니다.

## 16. GitHub에 첫 업로드

```powershell
git status
git add .
git commit -m "Initial disaster distributed analysis MVP"
git push origin main
```

기본 브랜치가 `master`로 생성된 경우:

```powershell
git branch -M main
git push -u origin main
```
