# TFBPShiny

A Shiny web application for exploring transcription factor binding and perturbation
data from the [Brent Lab yeast collection](https://huggingface.co/collections/BrentLab/yeastresources).

---

## Quick start (pip install)

Install from GitHub into a virtual environment:

```bash
python -m venv tfbpshiny-env
source tfbpshiny-env/bin/activate  # Windows: tfbpshiny-env\Scripts\activate
pip install git+https://github.com/BrentLab/tfbpshiny@dev
```

Run the app:

```bash
python -m tfbpshiny shiny
```

Options:

```bash
python -m tfbpshiny --log-level INFO shiny --port 8010 --host 127.0.0.1
```

---

## Local development (Poetry)

```bash
git clone https://github.com/BrentLab/tfbpshiny.git
cd tfbpshiny
poetry install
pre-commit install
```

Run in debug / hot-reload mode:

```bash
poetry run python -m tfbpshiny --log-level DEBUG shiny \
    --port 8010 --host 127.0.0.1 --debug
```

### Environment variables

Create a `.env` file in the repo root to override defaults:

```bash
# Optional — only needed for private HuggingFace datasets
HF_TOKEN=<your_huggingface_token>

# Optional — override the VirtualDB config path
VIRTUALDB_CONFIG=/path/to/custom_config.yaml
```

---

## Production deployment

### Prerequisites

- An AWS account with permissions to create EC2 instances, IAM roles,
  and security groups
- [Terraform](https://developer.hashicorp.com/terraform/install) ≥ 1.0
- An EC2 key pair already created in `us-east-2` (or your target region)
- DNS A records for `tfbindingandperturbation.com`,
  `www.tfbindingandperturbation.com`,
  and `shinytraefik.tfbindingandperturbation.com` pointed at the
  instance's public IP

### 1. Provision the EC2 instance

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars — set key_name and adjust instance_type / root_volume_gb
# if needed
terraform init
terraform apply
```

Note the `public_ip` output and update your DNS records to point at it.

### 2. Prepare environment files

The app requires two secret files that are **not** stored in the repository.
Create them locally, then copy them to the instance:

#### .envs/.production/.shiny

```bash
DOCKER_ENV=true
HF_TOKEN=<your_huggingface_token>       # optional; only for private HF datasets
VIRTUALDB_CONFIG=/path/to/config.yaml   # optional; defaults to bundled config
```

#### .envs/.production/.traefik

```bash
TRAEFIK_DASHBOARD_PASSWORD_HASH=<bcrypt_hash>
```

To generate a bcrypt hash for the Traefik dashboard:

```bash
docker run --rm httpd:alpine htpasswd -nbB admin 'yourpassword'
# Copy the hash portion (after "admin:") into the env file
```

Copy the env files to the instance:

```bash
scp -r .envs/ ec2-user@<public_ip>:/opt/tfbpshiny/
```

### 3. Build and start the stack

```bash
ssh ec2-user@<public_ip>
cd /opt/tfbpshiny
docker compose -f production.yml up -d --build
```

Traefik will automatically obtain a Let's Encrypt TLS certificate on first start.

### HuggingFace cache

The shinyapp container sets `HF_HOME=/hf-cache` and mounts a named Docker volume
there. HuggingFace model data is downloaded once and persists across container
rebuilds — no re-download on `docker compose up --build`.

### Logs

Application and Traefik logs are sent to AWS CloudWatch Logs under the log group
`/tfbpshiny/production` in `us-east-2`.

---

## Contributing

1. Fork the repository and clone your fork
1. Install dependencies: `poetry install && pre-commit install`
1. Switch to `dev`: `git switch dev`
1. Branch from `dev` — **not** `main`: `git switch -c my-feature`
1. Keep branches small and focused to make review easier
1. Rebase onto `dev` periodically: `git rebase dev`
1. When ready, open a pull request targeting the BrentLab `dev`
  branch — **not** `main`

### Running tests

```bash
poetry run pytest tests/unit/      # unit tests
poetry run pytest tests/e2e/       # end-to-end (requires Playwright)
poetry run pytest                   # all tests

# First-time Playwright setup
poetry run playwright install
```

### Code quality

```bash
poetry run black .
poetry run isort .
poetry run mypy .
```
