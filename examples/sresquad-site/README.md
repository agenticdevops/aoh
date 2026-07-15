# sresquad-site

Example SITE repository — the Ansible-inventory analog. Packs are portable (the WHO);
bindings here are site-specific (the WHERE): role × target. Keep real site repos
private; this one exists to demo the shape.

- `bindings/kubeops-sresquad.yaml` — binds `kubeops-copilot` (from
  `collections/core/kubeops`) to the local kind cluster `kind-sresquad-demo`.

Install: `aoh install-hermes-agent collections/core/kubeops --profile kubeops-sresquad --binding examples/sresquad-site/bindings/kubeops-sresquad.yaml`
