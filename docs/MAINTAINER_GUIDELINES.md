# Maintainer (Approver) Guidelines

This document outlines the process and requirements for becoming a maintainer (an "Approver")
for the openshift-virtualization-tests repository. The progression path is based on demonstrated
commitment, technical expertise, and, most importantly, community trust.

The progression is structured in two primary paths:

- **Reviewer → Component Approver (SIG Owner):** This path recognizes deep component mastery and
  proven quality guardianship. A candidate is expected to act as an active Reviewer for at least
  six months, contribute high-quality code, and, most critically, provide substantial reviews both
  within and outside their component.

- **Component Approver → Root Approver:** This level is reserved for senior members who have
  demonstrated holistic repository understanding, strategic leadership (e.g., CI/CD refactoring),
  and continuous, high-volume review work across the entire codebase for at least twelve months.

## Key Policy Points

- **Acceptance of Responsibility:** Candidates must explicitly accept and demonstrate a genuine
  desire to take on the full responsibilities of the role, including the commitment to ongoing,
  timely, and high-quality reviews.

- **Code Review is Mandatory:** The primary qualification for any Approver role is a proven,
  measurable track record of high-quality code review, which demonstrates system-wide understanding
  and ownership.

- **Mentorship is Required:** Becoming a Component Approver requires a structured, minimum
  three-month mentorship under an existing maintainer to ensure alignment on technical and
  community standards.

- **No Automatic Approval:** While meeting the measurable metrics is necessary, promotion is not
  automatic. The final decision rests with existing maintainers, who evaluate qualitative factors
  such as judgment, collaboration, and community leadership.

## Rationale: Why Code Review is the Path to Maintainership

In this project, moving up the ladder is not just about the code you contribute; it's about your
proven ability to protect the quality and stability of the entire repository. The role of an
Approver is one of trust and ownership. Code review is the only mechanism to demonstrate and
measure this.

- **It Builds Trust:** An Approver's `/approve` is a guarantee that a change is safe to merge.
  By consistently reviewing code, you provide a public, measurable track record of your judgment.
  Every bug you catch, every design flaw you spot, and every potential break you prevent builds
  trust with the existing maintainers.

- **It Proves Holistic Understanding:** Writing a PR proves you understand one problem. Reviewing
  all PRs (the key duty of a Component Approver) proves you understand the entire system. This is
  critical for catching cross-component issues (e.g., how a change in storage might break a
  networking test). You cannot become a Root Approver without this holistic view.

- **Helps with Maintainability:** When reviewing numerous changes, the ability to sustain the pace
  and remain effective over an extended period is contingent upon the maintainability of the code.

- **It Sharpens Your Own Technical Skills:** Reviewing code is one of the fastest ways to grow as
  an engineer.
  - You gain exposure to different approaches, patterns, and solutions to problems you may not
    have encountered.
  - You learn to identify common anti-patterns and pitfalls in others' code, which teaches you to
    avoid them on your own.
  - It forces you to read and understand parts of the codebase you didn't write, deepening your
    systemic knowledge.
  - You must articulate complex technical feedback, which solidifies your own understanding. In
    effect, to review is to teach, and to teach is to learn.

- **It Demonstrates Ownership:** Writing code is a contribution. Reviewing code is an act of
  ownership. It shows you care about the project's long-term health, not just your own features.
  This is the essential mindset of a maintainer.

- **It is Mentorship:** Your reviews are the primary way you mentor other contributors. Improving
  the quality of other people's code through constructive feedback is a core leadership function
  and a prerequisite for taking on more responsibility.

## Definitions of Roles

### Reviewer

Listed in the `reviewers` section of an OWNERS file. You review PRs, typically in your area
of expertise, and can use `/lgtm` (which is non-binding).

### Component Approver (SIG Owner)

Listed in the `approvers` section of a subdirectory OWNERS file (e.g., `tests/storage/OWNERS`).

- **Approval Power:** You can provide a binding `/approve` for PRs that only touch files within
  your component's directory.
- **Repository-Wide Responsibility:** You are now expected to review PRs submitted to the
  repository, regardless of the component, to build a holistic understanding of the codebase.

### Root Approver (Repo Approver)

The Repository Approver (or Root Approver) is the ultimate guardian of the project. This
individual holds the final authority over the repository's long-term health, test framework
consistency, and CI/CD infrastructure. Their primary duty is to prevent "test rot," flakiness,
and infrastructure decay, ensuring quality and trustworthy code. This authority is explicitly
defined in the project's root `OWNERS` file, superseding all other sub-directory owners.

- **Ultimate Approval and Veto:** Possesses the absolute right to `/approve` or `/hold` any
  change. This authority is used to enforce architectural standards, resolve disputes, or merge
  critical framework changes.
- **Final Escalation Point:** Acts as the "tie-breaker" in disputes between component owners.
- **CI/CD Infrastructure Ownership:** Owns and manages the core CI/CD pipelines (e.g., GitHub
  Actions and checks). They are responsible for ensuring the test infrastructure itself is not
  the source of failures.
- **Test Framework Stewardship:** Maintains the foundational test framework, shared libraries,
  and helper utilities, preventing technical debt and fragmentation in how tests are written.
- **Flakiness and Policy Enforcement:** Enforces strict standards for test reliability, including
  the policies used to identify, quarantine, and fix flaky tests.
- **Mentorship:** Mentors SIG Owner and Root Approver candidates.

## The Contributor Ladder

### Path 1: Reviewer → Component Approver

This path recognizes your mastery of a specific component and formally expands your responsibility
to include reviewing all repository pull requests.

#### Measurable Requirements

**Component Mastery (Depth):**

- Author a minimum of **15 significant PRs** to your target component. A "significant PR" adds
  new features or fixes a non-trivial bug, not just typos or basic code fixes.
  - *Technical Skill:* You can write high-quality, working code that adheres to the project's
    standards.
  - *Problem Solving:* You can independently tackle a complex bug or build a new feature from
    start to finish.
  - *Understanding the "How":* You know how to add code to the component.

- Author at least **30 substantial reviews** within that component, demonstrating deep expertise
  and the ability to mentor others.
  - *Deep Expertise:* You understand the component well, and you can identify subtle bugs,
    potential performance issues, or architectural flaws in someone else's logic.
  - *Guardianship:* You actively protect the project's quality by preventing bad code from being
    merged.
  - *Mentorship:* You can articulate why something is wrong and how to fix it in a constructive,
    educational way.
  - *Holistic View:* You ensure the new PR fits with the rest of the component and doesn't break
    other features.

**Sustained Activity (Time):**

- Act as an active Reviewer and contributor for no less than **6 months**.

**Initial Cross-Repo Review (Scope):**

- Provide substantial reviews on at least **15 significant PRs** outside of your target component.
  This demonstrates your willingness and ability to take on the role's core responsibility of
  reviewing all PRs.

**Demonstrated Ownership:**

- Be the primary person triaging issues, answering questions, and mentoring new contributors for
  your component.

#### Mentorship

Becoming a maintainer requires a structured, minimum **three-month** mentorship under an existing
maintainer. This period covers technical standards (code quality, testing, design) and community
skills (issue triaging, communication) across various release and contribution cycles.

**Mentor's Role:** The mentor actively guides and evaluates the candidate's PR review process.
Key responsibilities include:

- *Reviewing Reviews:* Meticulously checking the candidate's feedback and decisions on other
  contributors' PRs to ensure consistent quality standards.
- *Providing Feedback:* Offering detailed feedback on the clarity, accuracy, and policy adherence
  of the candidate's reviews.
- *Delegating:* Gradually assigning more complex and critical PRs to increase the candidate's
  responsibility.
- *Assessing Insights:* Evaluating the candidate's technical ability to identify issues, suggest
  improvements, enforce test requirements, and maintain architectural alignment.

**Candidate's Role:** The candidate must take initiative to:

- *Lead Reviews:* Take ownership of reviewing a significant volume of diverse PRs.
- *Demonstrate Diplomacy:* Interact professionally and clearly with contributors for a positive
  review process.
- *Learn and Adapt:* Quickly apply mentor feedback to subsequent reviews and contributions.
- *Contribute Code:* Continue submitting high-quality code to prove codebase mastery.

### Path 2: Component Approver → Root Approver

This path promotes you from reviewing all PRs to having the authority to approve all PRs. It
certifies you as a trusted maintainer for the entire repository. This role is reserved for senior
members with a holistic understanding of both the system under test and the test framework,
demonstrating exceptional judgment in managing the complex interplay between test stability and
development velocity.

#### Measurable Requirements

**Sustained Component Ownership (Time):**

- Serve as an active Component Approver for at least **12 months**.

**Fulfilled Repository-Wide Review Duty (Mandatory):**

- Demonstrate a consistent and high-quality review record across the entire repository.
  - *Metric:* Provide substantial reviews for a high percentage (e.g., **>75%**) of all PRs
    opened during your tenure as a Component Approver.
  - *Metric:* Author a minimum of **75 substantial reviews** outside of your primary component,
    showing your review work is not just superficial.
- Be a focal point for CI/CD issues (supported by your mentor).

**Strategic Leadership (Impact):**

- Successfully lead and land at least **2 major repository-wide efforts**. Examples:
  - A significant CI pipeline refactor.
  - Designing and implementing new repository-level features (e.g., conformance).
  - Resolving open repository issues and backlog items.

**Community Leadership:**

- Successfully mentor at least **1 other contributor** up to the Reviewer or Component Approver
  level.

#### Mentorship

The Root Approver candidate is mentored by an existing Root Approver. This mentorship focuses on
strategic decision-making, CI/CD ownership, and project governance.

**Mentor's Role:** Key responsibilities include:

- *Strategic Review:* Guide the candidate through high-level design decisions, framework
  refactors, and dispute resolution between Component Approvers.
- *CI/CD Delegation:* Gradually delegate ownership of CI/CD pipeline health, flakiness management,
  and tooling updates.
- *Policy Enforcement:* Ensure the candidate understands and applies repository-wide policies
  regarding test quality and architectural standards.

**Candidate's Role:** The candidate must actively demonstrate readiness for ultimate project
ownership by:

- *Resolving Conflicts:* Act as a shadow escalation point, proposing and defending solutions for
  disputes or major technical disagreements.
- *Driving Framework Stability:* Proactively identify and propose fixes for systemic issues in
  the test framework or CI infrastructure.
- *Strategic Communication:* Lead discussions about future test architecture and repository
  direction.
