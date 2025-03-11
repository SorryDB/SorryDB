# SorryDB and Leaderboard

This project creates a continuously updating benchmark and leaderboard based on
"sorry" statements in public Lean projects to stimulate the development and adoption of AI-assisted theorem proving in (formal) mathematics.

## Introduction

Automated (formal) theorem proving has the potential to make proof assistants such as Lean easier to use, and ultimately to become a useful tool in mathematical research. However, at the moment there is a significant gap between automated theorem proving "in the lab" and adoption by mathematicians in "real world" conditions. This project aims to help bridge this gap by setting up a continuously running competition evaluating the performance of AI theorem provers on proofs-in-progress in public Lean formalization repositories.

The key features of this system are

1. A focus on *research mathematics* (as opposed to competition mathematics), in all its diversity.
2. The use of new, not-yet-proven statements to minimize the impact of data contamination on evaluation.
3. A minimal gap from performing well in the competition to adoption in the real world.

This project was motivated by Jason Rute's talk [*The Last Mile*](https://www.youtube.com/watch?v=Yr8dzfVkeHg). It is much inspired by the [*miniCTX*](https://cmu-l3.github.io/minictx/) benchmark, the [*LeanAgent*](https://arxiv.org/abs/2410.06209) system, and the somewhat analoguous [*SWE-bench*](https://www.swebench.com/) for software engineering.

## Using sorry statements from public repositories

Mathematicians often collaborate on formal mathematics projects in Lean, hosting their work on GitHub. These works-in-progress frequently contain formally stated theorems with proofs deferred to later stages, marked by the `sorry` placeholder.

Such statements vary wildly in subject area and difficulty. They range from major theorems (perhaps the statement of the final target of the formalization project) to routine lemmas that follow easily from the relevant results in the `mathlib` library (but which the author has postponed filling in).

We propose to compare automated (formal) proof systems by testing their performance in proving such sorry statements. Advantages:

1. Sorry statements "in the wild" capture a wide range of different aspects of research mathematics.
2. Having a constant influx of *new* sorry statements mitigates the problem of data
   contamination.
3. Being able to fill a sorry in an ongoing formalization projection is almost
   by definition something that is useful to someone.

## System description

This project is work-in-progress. Below is a description of the intended final product.

We envision a setup consisting of a *database* of sorries, a *leaderboard* server serving sorries from the database, and competing *clients* implementing different theorem proving systems. Below we describe this in more detail.

### The database

*SorryDB* is a continuously updating database of sorry statements from public
Lean repositories. It locally reproduces and verifies these statements, ensuring
they compile correctly and represent mathematical propositions (with type
`Prop`), not definitions to be filled. The database stores all information
necessary to locally reproduce the sorry statements.

This provides a source of real-world problems for training and evaluating AI
theorem provers. The continuous influx of new problems helps mitigate training
data contamination.

### The leaderboard server

The *leaderboard server* manages the live competition by selecting recent open sorry statements from the database, serving them to competitors, and verifying their solutions. It maintains a live ranking of all participating clients.

Eventually, when competitors become sufficiently performant, the leaderboard could also generate automated pull requests to incorporate the generated proofs into their repositories.

### Client

Clients poll the server for sorry statements, reproduce them locally, and
attempt to prove them within the given time limit. Successful solutions are uploaded
back to the server. We plan to provide sample client implementations using various Lean
interaction tools to facilitate participation.

### Scoring

Traditional benchmark percentages don't adequately capture performance in this
context due to widely varying problem difficulty, inclusion of potentially unsolvable
statements, and asynchronous participation of competitors.

Instead, we propose an ELO-like rating system that measures relative performance, updating scores whenever one competitor solves a problem that another failed to prove.

