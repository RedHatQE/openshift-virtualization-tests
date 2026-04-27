# AI Contribution Policy

## Overview

This policy establishes guidelines for contributions that involve Artificial
Intelligence (AI) tools, including Large Language Models (LLMs), code generation
tools, and AI-assisted development environments.

This is a living document that will evolve as AI technology and legal frameworks
mature. It is based on the [KubeVirt AI Contribution Policy](https://github.com/kubevirt/community/blob/main/ai-contribution-policy.md).

## Motivation

AI tools can meaningfully accelerate test development, documentation, and code
review. This policy encourages their responsible use while ensuring transparency
and maintaining quality standards.

### Contributor Accountability

AI tools can produce plausible but incorrect test logic, over-engineered
scaffolding, or code that bypasses project conventions. Contributors are expected to:

- Thoroughly review and understand every line of AI-generated code before submission
- Refine AI output to meet project standards (see [`CONTRIBUTING.md`](CONTRIBUTING.md))
- Take full ownership of all submitted content regardless of origin

Low-effort submissions that appear to be unreviewed AI output may be rejected
without detailed feedback. This is particularly relevant for AI-assisted test
implementations, where subtle logical errors can produce tests that pass but
validate nothing.

### Legal and Copyright Rationale

Copyright law around AI-generated content continues to evolve. Disclosure helps:

- Maintain the integrity of the project's licensing
- Identify content that may originate from AI training data with unclear licenses
- Enable the community to track and refine practices as legal guidance develops

For further reading, see the [OpenInfra Foundation AI Policy](https://openinfra.org/legal/ai-policy/)
and [AI-Assisted Development and Open Source: Navigating Legal Issues](https://www.redhat.com/en/blog/ai-assisted-development-and-open-source-navigating-legal-issues).

## Disclosure Requirements

### Disclosure

All contributors **SHOULD** disclose AI tool use when submitting code,
documentation, or other content to this project.

Disclosure **SHOULD** take the form of a trailer line in the commit message.
The preferred format for this project is:

```
Assisted-by: Claude Sonnet 4.6 <noreply@anthropic.com>
```

Including the model name is **RECOMMENDED** to provide a precise record of the tool used.

All commits **MUST** also include a `Signed-off-by` trailer per the project's
DCO requirements:

```
Signed-off-by: Your Name <your@email.com>
```

### Scope of Disclosure

Disclosure is expected when AI tools have materially contributed to the submitted content.

**Requires disclosure:**

- AI wrote a function, class, fixture, or significant code block you included
- AI suggested an algorithm, test design, or architectural approach you adopted
- AI generated tests, docstrings, or commit messages you used
- AI-assisted debugging that shaped the final implementation

**Does not require disclosure:**

- General Q&A or learning, even if it informed your approach
- IDE autocomplete (line completions, IntelliSense)
- Using AI to explain existing code
- Asking AI to review human-written code
- Spell-checking or minor corrections
- Content substantially rewritten such that the original AI output is unrecognizable

When in doubt, err on the side of disclosure — transparency benefits the community.

## Recommended Uses

AI tools work well as development assistants for tasks such as:

- **Test scaffolding**: Generating boilerplate fixtures, conftest structure, and initial test stubs
- **Test authoring**: Writing test cases, test data, and coverage for known scenarios
- **STD drafting**: Writing Software Test Description docstrings from feature requirements
- **Refactoring**: Suggesting improvements to existing test or utility code
- **Documentation**: Drafting technical documentation and inline comments
- **Debugging**: Identifying potential issues and suggesting fixes
- **Research**: Exploring test approaches and best practices
- **Review assistance**: Checking compliance with project coding standards

This list is not exhaustive — contributors are encouraged to find other productive uses and share them with the community.

## Contributor Responsibilities

Contributors are responsible for ensuring all submitted content — regardless of
origin — meets project standards as defined in [`CONTRIBUTING.md`](CONTRIBUTING.md) and
[`CODING_AND_STYLE_GUIDE.md`](CODING_AND_STYLE_GUIDE.md), which cover:

- Coding conventions, type hints, and import rules
- Test design workflow (STP → STD → Implementation)
- Fixture guidelines and marker requirements
- Linter compliance (no suppressions permitted)
- Search-first development (reuse before writing new code)

AI tools **MUST NOT** be used to bypass these standards. In particular:

- ❌ Do not accept AI output that adds `# noqa`, `# type: ignore`, or linter suppressions
- ❌ Do not submit AI-generated tests without verifying marker completeness
- ❌ Do not submit AI-generated STD placeholders that skip the required docstring format
- ❌ Do not let AI generate raw YAML dicts or `subprocess.run` calls where project abstractions exist

## Legal and Licensing Considerations

Contributors must ensure that:

- AI tool terms of service do not conflict with this project's license
- No copyrighted material is inadvertently included in AI-generated output
- The Developer's Certificate of Origin (DCO) can be legitimately signed
- Use of AI tools complies with your employer's policies

## Review Process

Reviewers evaluate AI-assisted contributions by the same criteria as all others:

- Code quality and adherence to project standards
- Correct test logic and coverage of the intended scenario
- Appropriate fixture scope, markers, and dependency declarations
- Security implications and long-term maintainability

Reviewers **MAY** request clarification on AI-assisted changes where the
contributor's understanding of the code is not evident from the PR.

## AI Tool Configuration

This project uses [`AGENTS.md`](../AGENTS.md) as its AI agent configuration
file, compatible with the emerging [AGENT.md](https://agents.md)
standard. AI coding tools that support project-level configuration files should
be pointed at `AGENTS.md` for project-specific guidance.

## Policy Evolution

This policy will be reviewed and updated to reflect changes in AI capabilities,
legal developments, and community experience.

## Questions and Clarifications

For questions about this policy:

1. Open an issue in the [project repository](https://github.com/RedHatQE/openshift-virtualization-tests/issues)
2. Discuss with maintainers via a PR or issue comment

## References

- [KubeVirt AI Contribution Policy](https://github.com/kubevirt/community/blob/main/ai-contribution-policy.md)
- [Linux Foundation Generative AI Guidelines](https://www.linuxfoundation.org/legal/generative-ai)
- [OpenInfra Foundation AI Policy](https://openinfra.org/legal/ai-policy/)
- [QEMU Code Provenance Policy](https://www.qemu.org/docs/master/devel/code-provenance.html#use-of-ai-content-generators)
- [AGENT.md Standard](https://agents.md)
