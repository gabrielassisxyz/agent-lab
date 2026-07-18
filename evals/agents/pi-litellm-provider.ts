/**
 * Registers the local LiteLLM proxy as a `pi` provider.
 *
 * WHY this exists: the agent runs inside a container attached only to `--internal` docker
 * networks, so it has no route to the internet — that is the whole point of the sandbox. The
 * one thing it can reach is LiteLLM, which brokers the actual model call from outside. So the
 * agent's brain is reachable and its hands are not, which is the property the experiment needs.
 *
 * Both values are injected at run time rather than hardcoded, because the same extension is
 * used from the host (where LiteLLM is localhost:4000) and from inside the sandbox (where it is
 * the container's name on the internal network).
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
	pi.registerProvider("litellm", {
		name: "LiteLLM",
		baseUrl: process.env.LITELLM_BASE_URL ?? "http://litellm-litellm-1:4000/v1",
		apiKey: "$LITELLM_API_KEY",
		api: "openai-completions",
		authHeader: true,
		models: [
			{
				id: "kimi-k2.7",
				name: "Kimi K2.7 Code",
				reasoning: false,
				input: ["text"],
				// Cost is zeroed on purpose: it is billed through a subscription upstream, and a
				// fabricated price would end up in the results table looking like a measurement.
				cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
				contextWindow: 256000,
				maxTokens: 16384,
			},
		],
	});
}
