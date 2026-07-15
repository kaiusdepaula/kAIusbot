# ROCm + uv: Common pitfalls

## 1. Don't put `+rocm` in `project.dependencies`

PEP 508 doesn't allow local version identifiers (`+rocm7.2`) in dependency
specifiers. The wheel index already routes to the right builds, so the plain
version is enough:

```toml
# WRONG
"torch>=2.13.0+rocm7.2"

# RIGHT
"torch>=2.13.0"
```

## 2. `explicit = true` indexes don't serve transitive deps

If your pytorch-rocm index is `explicit = true`, uv only looks there for
packages listed in `[tool.uv.sources]`. Torch's transitive dep on
`triton-rocm` won't resolve unless you either:

- Add `triton-rocm` as a **direct dependency** AND put it in `[tool.uv.sources]`, or
- Set `explicit = false` (but then the rocm index leaks stale copies of common packages into resolution)

Direct dependency approach:

```toml
dependencies = [
    "torch>=2.13.0",
    "triton-rocm>=3.7.1",
]

[tool.uv.sources]
torch = [{ index = "pytorch-rocm" }]
triton-rocm = [{ index = "pytorch-rocm" }]

[[tool.uv.index]]
name = "pytorch-rocm"
url = "https://download.pytorch.org/whl/rocm7.2"
explicit = true
```

## 3. Platform markers are optional noise

Unless the project needs to run on non-ROCm machines, skip `platform_machine ==
'x86_64'` markers on deps and sources. Less config, same result.
