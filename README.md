# cad-sis3-orders — SIS 3 (Cloud Application Development)

Student: Kuatzhan Aliya · ID 23b151044 · Group Monday 11:00 · Region `eu-north-1`

A small orders system built completely as code (CloudFormation):

```
Client ──HTTP──► ALB ──► ECS Fargate "orders-api" ──publish──► SNS topic (OrderPlaced)
                                                                 │
                                                                 ▼
                                   DynamoDB ◄── Lambda consumer ◄── SQS queue ──(3 fails)──► DLQ
                                (orderId = dedup key)
```

| Week | Requirement | Where |
|------|-------------|-------|
| 9  | SQS queue with a DLQ and `maxReceiveCount` | `infra/app.yaml` → `OrdersQueue`, `OrdersDeadLetterQueue` |
| 9  | Domain event through SNS | `OrdersTopic`, `app/app.py` publishes `OrderPlaced` |
| 9  | Idempotent consumer, dedup key | `ConsumerFunction`: `orderId` + `attribute_not_exists(orderId)` |
| 10 | ECR: immutable tags, lifecycle policy | `infra/ecr.yaml` → `ImageRepository` |
| 10 | ECS Fargate behind an ALB, two separate roles | `Service`, `TaskExecutionRole`, `TaskRole` |
| 10 | CloudWatch logs with retention | `ServiceLogGroup`, `ConsumerLogGroup` (7/14/30 days by env) |
| 11 | Everything in CloudFormation, in git | `infra/` |
| 11 | Parameters for the environment, no secrets | `Env`, `ImageTag`, `Mappings: Sizing` |

## Files

- `app/app.py` — HTTP API (`GET /health`, `POST /orders`), `app/test_app.py` — unit tests
- `Dockerfile` — container image (non-root user)
- `infra/ecr.yaml` — shared registry + CodeBuild image build (deploy once)
- `infra/app.yaml` — the whole application stack (deploy any number of copies)

## Deploy (AWS CloudShell, region eu-north-1)

One time — the registry and the image build:

```bash
git clone https://github.com/aliyushaK/cad-sis3-orders.git && cd cad-sis3-orders
aws cloudformation deploy --stack-name sis3-registry --template-file infra/ecr.yaml --capabilities CAPABILITY_IAM
aws codebuild start-build --project-name sis3-registry-image-build   # or "Start build" in the console
```

**The one deploy command** (ImageTag = the commit SHA printed by the build):

```bash
aws cloudformation deploy --stack-name sis3-orders --template-file infra/app.yaml \
  --parameter-overrides Env=dev ImageTag=<commit-sha> --capabilities CAPABILITY_IAM
```

Reproducibility test — a second, independent copy is the same command with a new stack name:
`--stack-name sis3-orders-copy`.

## Try it

```bash
URL=$(aws cloudformation describe-stacks --stack-name sis3-orders --query "Stacks[0].Outputs[?OutputKey=='ServiceUrl'].OutputValue" --output text)
curl $URL/health
curl -X POST $URL/orders -H 'Content-Type: application/json' -d '{"orderId":"order-1","item":"book","qty":2}'
```

Sending the same `orderId` twice stores the order once (the consumer logs `duplicate-skipped`).

## CI/CD (Practice 7)

`.github/workflows/deploy.yml` runs on every push to `main`:

1. **test** — unit tests + `cfn-lint` (no AWS credentials yet)
2. **deploy** (GitHub Environment `production`) — gets 1-hour AWS credentials through **OIDC**
   (role from `infra/github-oidc.yaml`, no access keys stored anywhere), builds the image tagged with
   `$GITHUB_SHA`, pushes it to ECR and runs `aws cloudformation deploy` with `ImageTag=$GITHUB_SHA`.

Environment variables in GitHub (not secrets): `DEPLOY_ROLE_ARN`, `CFN_ROLE_ARN`, `ECR_REPO`.

## Redeploy before the defence (after teardown)

In CloudShell (eu-north-1):

```bash
git clone https://github.com/aliyushaK/cad-sis3-orders.git && cd cad-sis3-orders
aws cloudformation deploy --stack-name sis3-registry --template-file infra/ecr.yaml --capabilities CAPABILITY_IAM
```

Then in GitHub → Actions → **deploy** → **Run workflow** — the pipeline builds the image and creates `sis3-orders`.

## Clean up

```bash
aws cloudformation delete-stack --stack-name sis3-orders
aws cloudformation delete-stack --stack-name sis3-registry
```
