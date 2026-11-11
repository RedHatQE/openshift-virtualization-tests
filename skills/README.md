# Skills

Agent-harness skills vendored with this repository. Each subdirectory is a skill (a
`SKILL.md` with YAML frontmatter: `name`, `description`) that automates a workflow for
AI agents working on this repo. The skills concept and the `remote-debugging` skill are
ported from [mtv-api-tests PR #733](https://github.com/RedHatQE/mtv-api-tests/pull/733)
(by myakove — source: https://github.com/RedHatQE/mtv-api-tests/tree/main/skills).

## Available skills

| Skill | Purpose |
| --- | --- |
| `remote-debugging` | Attach an AI agent to a blocked remote debugger session (`CNV_REMOTE_PDB`) |

## Installation (manual — each user)

Skills are not auto-discovered from this folder. Symlink the skill you want into your agent
harness's skills directory — its location is harness-specific, so create it first if it does not
exist:

```bash
harness_skills_dir=<your harness skills directory>
mkdir -p "$harness_skills_dir"
ln -s /path/to/openshift-virtualization-tests/skills/remote-debugging "$harness_skills_dir/remote-debugging"
```

A project-local skills directory is preferred over a user-level one.

**Note:** most harnesses discover skills at session start, so a freshly created symlink
only takes effect after restarting the session.
