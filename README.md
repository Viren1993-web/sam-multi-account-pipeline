# How I Built a Reusable AWS SAM CI/CD Pipeline for Multi-Account Deployments

> **Build Once, Deploy Everywhere** — a single Docker image that standardises AWS SAM
> deployments across every environment and every team.

---

## The Problem

Our team had several serverless projects written in Node.js and Python. Every repository
contained its own pipeline YAML, its own AWS CLI installation steps, and its own
deployment scripts. When AWS SAM released a new version, we had to update every
repository individually.

The pain points were real:

- **Duplicated pipeline YAML** — every project copy-pasted the same 80 lines
- **Inconsistent tooling** — different projects ran different SAM CLI versions
- **Slow builds** — every pipeline installed the AWS CLI from scratch
- **Difficult onboarding** — new engineers had to understand the pipeline *and* the app
- **Security drift** — IAM configuration varied across projects

I wanted to solve this once, for every project, forever.

---

## What I Wanted to Achieve

```
Developer pushes code
        │
        ▼
GitHub Actions Pipeline
        │
        │  pulls image
        ▼
Shared Docker Image (Amazon Public ECR)
        │
        │  sam build + sam deploy
        ▼
  STS AssumeRole
        │
   ┌────┴────┐
   ▼         ▼
AWS Dev    AWS Prod
Account    Account
```

**Goals:**

- ✅ One deployment image — all projects use it
- ✅ Multi-account — dev, staging, and prod from one pipeline run
- ✅ Support Node.js and Python runtimes
- ✅ No long-lived credentials — OIDC + STS AssumeRole
- ✅ Zero duplicated pipeline YAML

---

## Architecture

The solution has two moving parts:

### 1. The Deployment Image

A Docker image published to **Amazon Public ECR** that contains every tool needed to
deploy a SAM application:

| Tool | Purpose |
|------|---------|
| AWS SAM CLI | `sam build` and `sam deploy` |
| AWS CLI | Credential operations |
| nvm | Manage Node.js versions |
| pyenv | Manage Python versions |
| Python 3.14 | Runtime for the pipeline engine |

Because the image is **publicly available**, any GitHub Actions workflow can pull it
without authentication. There is no per-project installation step.

### 2. The Pipeline Engine

A small Python package (`sam_pipeline`) that runs *inside* the container. It:

1. Reads environment variables
2. Validates inputs
3. Installs the correct Node.js / Python version
4. Assumes an IAM role in each target account using STS
5. Runs `sam build` then `sam deploy`

---

## Building the Deployment Image

The Dockerfile uses a **multi-stage build** to keep the final image lean.

```dockerfile
# Stage 1 — build tools and install dependencies
FROM ubuntu:26.04 AS builder

ARG NVM_VERSION=v0.39.7
ARG PYTHON_VERSION=3.14.0

ENV NVM_DIR=/opt/nvm
ENV PYENV_ROOT=/opt/pyenv
ENV PATH=${PYENV_ROOT}/shims:${PYENV_ROOT}/bin:${PATH}

# Install nvm
RUN mkdir -p ${NVM_DIR} \
 && curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/${NVM_VERSION}/install.sh | bash

# Install pyenv + Python
RUN git clone --depth=1 https://github.com/pyenv/pyenv.git ${PYENV_ROOT} \
 && pyenv install ${PYTHON_VERSION} \
 && pyenv global ${PYTHON_VERSION}

# Install AWS SAM CLI and the pipeline engine
RUN pip install --no-cache-dir aws-sam-cli
COPY requirements.txt pyproject.toml /tmp/
COPY sam_pipeline /tmp/sam_pipeline
RUN pip install --no-cache-dir /tmp

# Stage 2 — minimal runtime image
FROM ubuntu:26.04
COPY --from=builder /opt/nvm /opt/nvm
COPY --from=builder /opt/pyenv /opt/pyenv
COPY pipe.yml /opt/sam-pipeline/pipe.yml

ENTRYPOINT ["python", "-m", "sam_pipeline"]
```

The key advantages:

- Every deployment uses **identical, pinned tooling**
- No installation during CI — the image is pre-baked
- **Faster builds** — pulling a 500 MB image is faster than installing 10 tools
- One place to update a tool version — one rebuild — every project gets the update

---

## Publishing to Amazon Public ECR

I chose **Amazon Public ECR** so any project can pull the image without credentials:

```bash
docker pull public.ecr.aws/z7q5l7x5/sam-pipeline:latest
```

Compare this with the old approach where every project did:

```yaml
# Old — every repository had this
- apt-get install -y curl unzip
- curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
- unzip -q awscliv2.zip && ./aws/install
- pip install aws-sam-cli
```

With the shared image, each project's pipeline shrinks to just:

```yaml
container:
  image: public.ecr.aws/z7q5l7x5/sam-pipeline:latest
```

The GitHub Actions workflow that builds and publishes the image uses OIDC:

```yaml
- name: Configure AWS credentials (OIDC)
  uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: arn:aws:iam::ACCOUNT_ID:role/DeployerAccess-Github
    aws-region: us-east-1

- name: Login to Amazon Public ECR
  run: |
    aws ecr-public get-login-password --region us-east-1 \
      | docker login --username AWS --password-stdin public.ecr.aws

- name: Build and push
  run: |
    docker build -t public.ecr.aws/z7q5l7x5/sam-pipeline:${{ github.ref_name }} .
    docker push public.ecr.aws/z7q5l7x5/sam-pipeline:${{ github.ref_name }}
```

---

## Multi-Account Deployment

This is the most valuable part of the solution.

### The Trust Relationship

Each target AWS account has an IAM role called `DeployerAccess`. Its trust policy
allows the **pipeline account** (the account that runs the pipeline) to assume it:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::PIPELINE_ACCOUNT_ID:root"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "sam-pipeline"
        }
      }
    }
  ]
}
```

### How the Pipeline Assumes the Role

```python
def assume_role_session(account_id: str, region: str, role_name: str) -> boto3.Session:
    sts = boto3.client("sts")
    response = sts.assume_role(
        RoleArn=f"arn:aws:iam::{account_id}:role/{role_name}",
        RoleSessionName="sam-pipeline",
    )
    return boto3.Session(
        aws_access_key_id=response["Credentials"]["AccessKeyId"],
        aws_secret_access_key=response["Credentials"]["SecretAccessKey"],
        aws_session_token=response["Credentials"]["SessionToken"],
        region_name=region,
    )
```

The credentials are then injected into the `sam deploy` subprocess environment — the
SAM CLI never needs to know about the role assumption.

### Security Best Practices

- **No long-lived credentials** — OIDC tokens expire after 15 minutes
- **Least privilege** — `DeployerAccess` only has the permissions needed for SAM
- **Explicit trust** — the target account explicitly trusts the pipeline account
- **Session tokens** — every deployment uses short-lived, scoped credentials

### Deploying to Multiple Accounts

Specify accounts via a **GitHub Actions Variable** (`Settings → Variables → New repository variable`):

| Variable name | Example value |
|---|---|
| `AWS_ACCOUNT_IDS` | `111122223333:us-east-1,444455556666:ap-southeast-2` |

Then reference it in the workflow:

```yaml
env:
  AWS_ACCOUNT_IDS: ${{ vars.AWS_ACCOUNT_IDS }}
```

Account IDs are not secrets, but storing them as Variables keeps them out of workflow
YAML — you update them in one place (GitHub settings) without touching code.

For a single account, use `AWS_ACCOUNT_ID` + `AWS_REGION` as Variables the same way:

```yaml
env:
  AWS_ACCOUNT_ID: ${{ vars.AWS_ACCOUNT_ID }}
  AWS_REGION: ${{ vars.AWS_REGION }}
```

---

## Supporting Multiple Languages

Instead of maintaining separate Node.js and Python pipelines, the same image handles
both. Only the runtime configuration changes.

**Node.js project:**

```yaml
env:
  RUNTIME_LANGUAGE: nodejs
  NODE_VERSION: "24"
```

**Python project:**

```yaml
env:
  RUNTIME_LANGUAGE: python
  PYTHON_VERSION: "3.14.0"
```

Internally, the `setup-environment.sh` script installs the correct version using nvm
(for Node.js) or pyenv (for Python):

```bash
nvm install "${node_version}"

if [[ "${runtime_language}" == "python" ]]; then
  pyenv install "${python_version}" --skip-existing
fi
```

---

## Repository Structure

This is all any project needs:

```
my-service/
├── template.yaml          # SAM template
├── samconfig.toml         # SAM deploy defaults (optional)
├── src/
│   └── handler.js         # Lambda function code
└── .github/
    └── workflows/
        └── deploy.yml     # 30 lines, not 80
```

And the pipeline YAML for that project:

```yaml
name: Deploy

on:
  push:
    branches: [main]

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    container:
      image: public.ecr.aws/z7q5l7x5/sam-pipeline:1.0.0

    steps:
      - uses: actions/checkout@v4

      - name: Deploy
        env:
          # Stored in GitHub Actions Variables — never hardcoded in YAML
          AWS_ACCOUNT_IDS: ${{ vars.AWS_ACCOUNT_IDS }}
          RUNTIME_LANGUAGE: nodejs
          NODE_VERSION: "24"
          STACK_NAME: my-service
          ACTIONS_ID_TOKEN_REQUEST_URL: ${{ env.ACTIONS_ID_TOKEN_REQUEST_URL }}
          ACTIONS_ID_TOKEN_REQUEST_TOKEN: ${{ env.ACTIONS_ID_TOKEN_REQUEST_TOKEN }}
          CI: "true"
        run: python -m sam_pipeline
```

That is the entire deployment configuration for a project. No AWS CLI installation.
No SAM CLI installation. No credential management. Just environment variables.

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AWS_ACCOUNT_ID` | One of these two | — | Single account ID to deploy to |
| `AWS_ACCOUNT_IDS` | One of these two | — | Comma-separated `ACCOUNT_ID:REGION` list |
| `AWS_REGION` | No | `us-east-1` | Default region (used with `AWS_ACCOUNT_ID`) |
| `DEPLOYER_ROLE_NAME` | No | `DeployerAccess` | IAM role name to assume in each account |
| `RUNTIME_LANGUAGE` | No | `nodejs` | `nodejs` or `python` |
| `NODE_VERSION` | No | `24` | Node.js version (nvm version string) |
| `PYTHON_VERSION` | No | `3.14.0` | Python version (pyenv version string) |
| `WORKING_DIRECTORY` | No | `.` | Path to the SAM project root |
| `STACK_NAME` | No | repo name | CloudFormation stack name |
| `SAM_ADDOPTS` | No | `""` | Extra arguments passed to `sam deploy` |
| `DEBUG` | No | `false` | Enable verbose logging |

---

## The Result

After rolling this out across our projects:

- **One place to update tooling** — bump the image tag everywhere at once
- **Consistent deployments** — every project uses the same SAM CLI version
- **30-line pipelines** instead of 80+ line pipelines
- **Faster onboarding** — engineers understand the app, not the pipeline
- **Security by default** — OIDC + AssumeRole, no stored credentials

The pattern is simple enough to explain in a 15-minute onboarding session and
powerful enough to handle production workloads across multiple AWS accounts.

---

## Getting Started

### 1. Clone this repository

```bash
git clone https://github.com/Viren1993-web/sam-multi-account-pipeline
cd sam-multi-account-pipeline
```

### 2. Build and publish the Docker image

Set the following GitHub Actions variables in your repository settings:

| Variable | Description |
|----------|-------------|
| `AWS_ACCOUNT_NUMBER` | Account ID where Public ECR lives |
| `ECR_ALIAS` | Your Public ECR alias |

Then tag a release:

```bash
git tag 1.0.0 && git push origin 1.0.0
```

### 3. Create `DeployerAccess` in each target account

The role needs at least these permissions for SAM:

- `cloudformation:*`
- `s3:*` (for the SAM deployment bucket)
- `iam:PassRole`
- The permissions your Lambda functions and other resources require

### 4. Use the image in your projects

See the [example/nodejs](./example/nodejs) and [example/python](./example/python)
directories for complete working examples.

---

## Local Development

```bash
# Install dev dependencies
make install-dev

# Run lint + type check + tests
make all

# Build the Docker image locally
make docker-build

# Open a shell in the container
make docker-shell
```

---

## Licence

MIT
