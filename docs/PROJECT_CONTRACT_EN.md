# PegineLab Project Contract v1

YadroKreator supports manually opted-in **observe** and **build-candidate** projects. GitHub repositories do not auto-appear as build profiles. In build mode, a versioned peginelab.project.json must be present in the selected GitHub branch and is validated at a pinned Git SHA. A valid manifest describes hardware, toolchain, expected artifacts and requested adapter, but **never grants permission to execute arbitrary scripts**. A reviewed factory-side adapter is required before a new build can actually run.

The extensible contract uses schema peginelab.project.v1, project (name, repository, branch, mode), optional platform, targets, docs, description, monitoring, and namespaced extensions. Build candidates additionally require pipeline.adapter and outputs. pipeline.entrypoint is documentation only. See the Russian guide for complete build/observation examples and safety rules. Existing WIFICAM and Irila workflows remain independent.
