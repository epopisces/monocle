# Developing this Application

I had iterated on creating this app in my personal life for some time.  I had just finished an iteration that produced a working model usingMicrosoft Agent Framework + Ollama when I encountered Nate B Jones [Monocle concept](https://www.youtube.com/watch?v=2JiMmye2ez), which took the knowledge layer and placed it behind an MCP server for speed, modularity, and to avoid vendor lock-in.  This drove another start-from-scratch.


This application was developed in large part through GitHub Copilot.  I spent a decent amount of time in the planning stage, defining the architecture, milestones, and technical spikes to validate assumptions before writing code.  At the conclusion of that stage I had different models evaluate my design and identify potential gaps, issues or improvements to the plan and design.

# Preparing this repository for GitHub Copilot

Process:
1. Create folder, open in VSCode
2. Initialize git: `git init`
3. Create a VSCode workspace: `Ctrl+Shift_P > Workspaces: Save Workspace As...`
4. Using GitHub Copilot Custom Agents (instructing the agent to emulate specialists such as Product Manager, UX Designer, Cybsersecurity Expert, Development Architect) draft PRD, UI Design, and SRS documentation, as well as a build plan.  Some things that were important to me:
   1. Debugging in VSCode.  I included the creation and maintenance of 
5. Create a local index `Ctrl+Shift+P → Chat: Build Local Workspace Index` (since this was not an AzDO or GitHub project which support remote index)

# References
- Nate B Jones [Build Your Monocle](https://promptkit.natebjones.com/20260224_uq1_guide_main)
- Nate B Jones [Monocle Companion Prompts](https://promptkit.natebjones.com/20260224_uq1_promptkit_1)

---

# GitHub Copilot Action Log Summary

## 2026-03-14 – Claude Sonnet 4.6
- Cross-referenced Gnomish design docs against Monocle docs and identified 8 improvements worth porting
- Updated `docs/ui-design.md`: added weight-driven edge visual encoding spec (thickness 0.5–5 px, opacity 30–100 %), typed edge color table (structured / wikilink / co-mention), Export PNG control, modifier-key sidebar navigation (`Ctrl+Click`, `Shift+Click`), three-tier backlinks panel description, multi-pane state reservation note in Application Shell, review-pending amber pulse on graph nodes, and inline text-selection mini-toolbar for expanded graph nodes
- Updated `docs/srs.md`: expanded FR-WEB-07 with all graph visual requirements (edge encoding, edge types, node pulse, node expand + text selection, export); added `edge_type` field to FR-API-13 graph edge response and updated explanation paragraph; added `link_type` field and three-tier description to FR-API-12a backlinks response
