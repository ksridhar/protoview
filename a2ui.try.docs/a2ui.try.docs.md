## /.well-known/agent-card.json

**Q** Explain "/.well-known/agent-card.json" in the context of A2A

In the context of **A2A (Agent-to-Agent)** communication, the `/.well-known/agent-card.json` file acts as a digital business card and a "handshake" protocol for AI agents.

As we move toward an ecosystem where your AI agent needs to talk to a restaurant's booking agent or a vendor’s support agent, we need a standardized way for them to identify, verify, and understand each other's capabilities without human intervention.

### Resources

- [Well known URI](https://en.wikipedia.org/wiki/Well-known_URI)
- [Well known URIs - IANA](https://www.iana.org/assignments/well-known-uris/well-known-uris.xhtml)

### What is it exactly?

The `/.well-known/` directory is a web standard (RFC 8615) used for site-wide metadata. The `agent-card.json` file specifically provides a machine-readable manifest that defines an AI agent's **identity, technical constraints, and safety policies.**

Think of it as the **robots.txt for the AI era**, but instead of just saying "don't crawl this," it says "here is how to interact with me safely."

#### Key Components of an Agent Card

Typically, this JSON file includes:

* **Identity & Ownership:** Who operates the agent (e.g., "Company X") and its unique identifier.
* **Capabilities:** What the agent can actually do (e.g., "scheduling," "payment processing").
* **Model Information:** Which LLM or version the agent is running, which helps the "calling" agent adjust its complexity or formatting.
* **Safety & Compliance:** Links to privacy policies, terms of service, and "human-in-the-loop" triggers.
* **Authentication:** Public keys or endpoint URLs for secure, encrypted A2A communication.

### Why is it crucial for A2A?

In a world of trillions of automated interactions, the `agent-card.json` solves three major problems:

| Problem | How Agent Card Solves It |
| --- | --- |
| **Trust** | It provides a "Verified" status. An agent can check the card to ensure it's talking to a legitimate business entity. |
| **Interoperability** | It defines the "language" (protocols) the agent speaks, preventing "hallucinated" API calls. |
| **Safety** | It sets boundaries. If an agent tries to perform an action not listed in the card, the interaction can be automatically blocked. |

### A Simple Example

If you were to look at a hypothetical `agent-card.json`, it might look something like this:

```json
{
  "agent_id": "com.example.concierge-v1",
  "name": "ExampleCorp Travel Assistant",
  "version": "2.0.4",
  "capabilities": ["booking", "itinerary-lookup"],
  "endpoints": {
    "api_url": "https://api.example.com/v1/agent"
  },
  "safety": "https://example.com/ai-policy"
}

```

### The Big Picture

As A2A becomes more common, these files will likely be indexed by "Agent Registries." Instead of searching Google for a website, your agent will search these registries for an `agent-card.json` that matches your request, effectively "hiring" another agent to complete a task for you.

---


