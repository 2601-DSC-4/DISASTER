# Final Demo Scenario: KEDA Queue-based Worker Autoscaling

이 문서는 최종발표에서 RabbitMQ queue length 기반 자동 scale-out 효과를 보여주기 위한 실행 순서입니다.

## 핵심 메시지

- Backend는 업로드 요청을 바로 RabbitMQ `image.task.queue`에 넣고 응답합니다.
- `analysis-worker`는 큐에서 이미지를 하나씩 가져와 분석하고 결과를 `analysis.result.queue`로 보냅니다.
- Aggregator는 분석 결과를 Redis에 저장하고 Dashboard가 Redis/RabbitMQ 상태를 보여줍니다.
- KEDA는 `image.task.queue` 길이를 5초마다 확인하고 `analysis-worker`를 1개에서 최대 5개까지 자동 조절합니다.

## 화면 배치

1. RabbitMQ Management UI: `http://<NODE_IP>:31672`
   - 로그인: `disaster / disasterpass`
   - Queues 탭에서 `image.task.queue` 메시지 수를 확인합니다.
2. Dashboard: `http://<NODE_IP>:30000`
   - 현재 큐 길이, 총 제보, 평균 처리 시간, 최근 worker ID를 확인합니다.
3. 터미널:
   - `kubectl get pods -n disaster-system -w`
   - worker pod가 1개에서 여러 개로 늘어났다가 다시 줄어드는 장면을 보여줍니다.

## 1. k3s와 KEDA 준비

```bash
curl -sfL https://get.k3s.io | sh -
sudo kubectl get nodes
```

Helm이 없다면 먼저 설치합니다.

```bash
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

KEDA를 설치합니다.

```bash
bash scripts/install-keda.sh
```

## 2. 이미지 빌드 및 k3s import

```bash
docker compose build
docker save disaster-backend:latest disaster-worker:latest disaster-aggregator:latest disaster-simulator:latest disaster-dashboard:latest -o disaster-images.tar
sudo k3s ctr images import disaster-images.tar
```

## 3. 기본 시스템 배포

KEDA CRD가 먼저 설치되어 있어야 `ScaledObject`가 적용됩니다.

```bash
kubectl apply -k k8s
kubectl get pods -n disaster-system
kubectl get scaledobject -n disaster-system
```

초기 상태에서 `analysis-worker`는 1개입니다.

```bash
kubectl get deployment analysis-worker -n disaster-system
```

## 4. Normal Mode

목표: 업로드 속도가 낮아서 큐가 거의 쌓이지 않는 모습을 보여줍니다.

```bash
kubectl delete job upload-simulator-normal -n disaster-system --ignore-not-found
kubectl apply -f k8s/jobs/normal-simulator-job.yaml
kubectl logs -f job/upload-simulator-normal -n disaster-system
```

확인 포인트:

- RabbitMQ `image.task.queue` 메시지 수가 0 근처를 유지합니다.
- Dashboard의 현재 큐 길이가 거의 증가하지 않습니다.
- `kubectl get pods -n disaster-system`에서 worker는 1개 근처를 유지합니다.

## 5. Disaster Mode

목표: 업로드 속도를 올려 큐가 쌓이고, KEDA가 worker를 자동으로 늘리는 모습을 보여줍니다.

터미널 하나에서 pod 변화를 계속 관찰합니다.

```bash
kubectl get pods -n disaster-system -w
```

다른 터미널에서 재난 부하를 실행합니다.

```bash
kubectl delete job upload-simulator-disaster -n disaster-system --ignore-not-found
kubectl apply -f k8s/jobs/disaster-simulator-job.yaml
kubectl logs -f job/upload-simulator-disaster -n disaster-system
```

확인 포인트:

- RabbitMQ Management UI에서 `image.task.queue` 메시지가 증가합니다.
- KEDA가 `analysis-worker` pod를 최대 5개까지 늘립니다.
- worker가 늘어난 뒤 큐 길이가 빠르게 감소합니다.
- 부하가 끝나고 큐가 비면 cooldown 이후 worker가 다시 1개로 줄어듭니다.

## 6. 발표 멘트 흐름

1. "평상시에는 요청량이 낮아서 worker 1개만으로 충분합니다."
2. "재난 상황에서는 업로드 요청이 급증하면서 RabbitMQ 큐가 완충 역할을 합니다."
3. "기존 수동 scale 방식 대신 KEDA가 `image.task.queue` 길이를 보고 자동으로 worker 수를 늘립니다."
4. "worker가 늘어나면 병렬 처리량이 증가하고 큐 길이가 다시 줄어듭니다."
5. "부하가 사라지면 KEDA가 worker를 다시 기본 1개로 줄여 자원을 아낍니다."

## 7. 정리 명령

```bash
kubectl delete -f k8s/jobs/disaster-simulator-job.yaml --ignore-not-found
kubectl delete -f k8s/jobs/normal-simulator-job.yaml --ignore-not-found
kubectl delete -k k8s
```
