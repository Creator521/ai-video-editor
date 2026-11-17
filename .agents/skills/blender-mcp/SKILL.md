---
name: blender-mcp
description: Plan and produce Blender 3D assets or scenes through the community MCP integration when Blender is installed and connected. Use for 3D reconstructions, maps, camera paths, or title elements.
---

# MCP for Blender

This is a community integration that lets an MCP client control Blender. It is an external tool integration, not a Python dependency or an editor feature. Use it to create or revise Blender scenes, then render deliverable frames/video for the editor to assemble.

## Workflow

1. Confirm Blender and the MCP server are available in the active client before promising direct scene control.
2. Build the requested scene with explicit camera, lighting, render resolution, frame range, and output path. Save the `.blend` project with rendered assets.
3. Render and review representative frames for composition, visual accuracy, render artifacts, and continuity.
4. Pass rendered media into the project's established FFmpeg assembly flow.

For a new Codex setup, upstream documents `uvx mcp-for-blender setup` as the guided installer, or manual setup with `uvx mcp-for-blender` and `uvx mcp-for-blender install-addon`. The installer modifies external MCP-client configuration and Blender add-ons; this project guide does not run it or claim that integration is connected. Follow the upstream install instructions and restart the client/Blender as directed.

Source: https://github.com/ahujasid/mcp-for-blender
