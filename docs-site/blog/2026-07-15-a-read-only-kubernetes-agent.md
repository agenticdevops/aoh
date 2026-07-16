---
title: A Kubernetes agent that can't kubectl delete
authors: [gourav]
tags: [kubernetes, safety]
date: 2026-07-15
---

More from the build log — [Field Note #1](https://agenticops.tv) talked about the shape of the harness; this one's about proving a guardrail is real instead of just asserting it.

<!-- truncate -->

I wanted to answer one question honestly: if I tell an AOH pack its agent is `kubectl-readonly`, is that a comment or is it true? "Instructed not to delete things" and "physically incapable of deleting things" are very different claims, and I only wanted to ship the second one.

The answer ended up living outside the agent entirely. `install-hermes-agent --binding` now generates a `provision.sh` that a human runs once, by hand — AOH never touches the cluster itself, it only writes files. That script creates a dedicated `ServiceAccount`, a `ClusterRole` scoped to `get`/`list`/`watch`, binds them together, and writes a scoped `kubeconfig`. The agent launches with that kubeconfig, not yours.

Then I proved it without the agent anywhere in the loop. Same kubeconfig, two commands, on a real `kind` cluster:

```
kubectl --kubeconfig "$KC" get pods -A                                        # works
kubectl --kubeconfig "$KC" delete pod coredns-668d6bf9bc-kw88m -n kube-system  # Forbidden
```

The API server itself rejected the delete — `Error from server (Forbidden): ... cannot delete resource "pods"`. Nothing about how the request was made changed between the two calls; only the RBAC attached to the identity that sent it. That's the guardrail I wanted: it lives in the target platform, not in a prompt telling the agent to behave.

While that provision-script generator was under final review, a real bug surfaced: binding values (context names, namespaces) were being interpolated straight into bash without validation — a textbook shell-injection opening if a binding file ever came from somewhere less trusted than my own repo. The fix was a strict allowlist regex on every value before it touches the generated script, with a `PackError` if anything outside `[A-Za-z0-9._-]` shows up. Caught before it shipped, but a good reminder that "generates a shell script" is a security-sensitive code path, review or no review.

Full walkthrough, copy-pasteable commands, and the honesty note about what "read-only" doesn't cover: [the kubeops-readonly tutorial](/docs/tutorials/kubeops-readonly). If you've got a `kind` cluster lying around, try it — watch the API server say no.
