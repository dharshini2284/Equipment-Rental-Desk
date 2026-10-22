# PROMPTS.md — AI Assistance Log

## 1. Overview

I developed the Equipment Rental Desk application for the KJBN Labs Software Engineering Internship Assignment between 17 and 22 October 2026. I used Claude Code (Anthropic, Claude Opus 5.5) in VS Code as a development assistant.

My workflow involved understanding the assignment, breaking the requirements into implementation tasks, reviewing the application locally, identifying gaps, and iteratively improving the backend, frontend, testing, and deployment. I used AI assistance for coding, debugging, and exploring implementation approaches, while making decisions about the application's requirements, functionality, interface, and development priorities.

I also tested the application locally, investigated startup and deployment problems, and handled the hosting configuration. I retained control of the Git workflow and made the commits myself.

## 2. Development Prompt Log

| No. | Date | Development task and prompt summary | Outcome and my involvement |
| --- | --- | --- | --- |
| 1 | 17 October 2026 | Worked through the two assignment PDFs to establish the application's required functionality, technical structure, business rules, and development standards. | Used the requirements to guide implementation and review the application against the assignment brief. |
| 2 | 17 October 2026 | Shared the Docker startup error after running `docker compose up --build`, where port 8080 was already occupied. | Investigated the local environment issue, corrected the startup guidance, and updated the README with alternative PowerShell port configuration. |
| 3 | 17 October 2026 | Asked for a personal checklist showing the requested functionality, implemented features, testing approaches, and remaining tasks. | Used the resulting `PROJECT_NOTES.md` as a private development and testing checklist. The file is excluded from Git. |
| 4 | 17 October 2026 | Reviewed the initial interface and requested a more polished, attractive user experience. | Improved the layout with a sidebar, dashboard, equipment cards, loan progress indicators, and a member profile page. |
| 5 | 19 October 2026 | Reviewed the remaining scope and requested implementation of the stretch features and addressable gaps. | Added a waitlist, SMS-stub outbox, PDF statements, equipment editing and deletion, and browser tests. Some features remained outside the implemented scope and were documented accordingly. |
| 6 | 20–21 October 2026 | Worked through deployment troubleshooting using short prompts and screenshots, first for Render and subsequently for Netlify. | Configured the hosting services, connected the repository, resolved a database resource conflict, set environment variables, and authorised the frontend deployment. Used AI assistance to troubleshoot deployment issues and check the deployed application. |
| 7 | 22 October 2026 | Requested a review of the submission documentation to improve clarity, align it with the brief, and accurately describe the development process. | Revised the README, submission document, and AI assistance log to use clearer language and distinguish my work from AI-generated contributions. |

## 3. My Development Workflow

I approached the project as an iterative engineering task rather than treating the initial implementation as the final result.

- **Requirements and implementation:** I used the assignment brief to identify the required application behaviour and guide implementation decisions.
- **Validation:** I ran the application locally, examined errors, and used test results to identify issues requiring further work.
- **Debugging:** I shared relevant terminal output and screenshots when problems occurred and evaluated the resulting fixes.
- **UI refinement:** I reviewed the initial interface and requested changes to make the application more usable and visually consistent.
- **Feature completion:** I revisited the remaining requirements and requested additional functionality where it could be implemented within the available time.
- **Deployment:** I handled the hosting-dashboard configuration and used AI assistance to troubleshoot deployment issues.
- **Final review:** I checked the documentation against the implemented functionality and retained known limitations rather than presenting every requirement as complete.

## 4. AI Assistance Disclosure

Claude Code assisted with code generation, tests, configuration, debugging, and documentation. I supplied development instructions, reviewed the application, made decisions about scope and presentation, tested it locally, and carried out the deployment-dashboard steps.

I used the assistant as part of an iterative development workflow and evaluated its output through application runs, tests, and manual checks. The repository and accompanying documentation provide the details of the implemented functionality and its verification status.
