FROM ghcr.io/astral-sh/uv:0.11.29 AS uv

FROM public.ecr.aws/lambda/python:3.12 AS dependencies
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /build
COPY pyproject.toml uv.lock ./
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_LINK_MODE=copy
RUN uv sync --locked --no-dev --no-install-project --python /var/lang/bin/python3.12

FROM public.ecr.aws/lambda/python:3.12
COPY --from=dependencies /opt/venv /opt/venv
COPY src/ ${LAMBDA_TASK_ROOT}/src/
ENV PYTHONPATH="/opt/venv/lib/python3.12/site-packages:${LAMBDA_TASK_ROOT}"
CMD ["src.s3_ingestion_handler.lambda_handler"]
