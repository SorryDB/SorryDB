# SorryDB and Leaderboard

This project aims to stimulate the development of AI tools to assist theorem
proving in Lean, by building a continuously updating benchmark and leaderboard
based on *sorry* statements in ongoing public Lean projects.

## Limitations of benchmarks for theorem proving

Benchmarks have been a key driver to breakthroughs
in image recognition, and still play an important role in much contemporary
research in AI. However, in the context of theorem proving 

1. Many benchmarks tend to focus on *competition mathematics*, which is not very
   representative for the kind of theorem proving occurring in typical *research
   mathematics*.

It is not that theorem proving in research mathematics is always
harder, but it is certainly far more heterogeneous. It may require a routine calculation,
or finding a relevant lemma in an obscure publication, or adapting a well-known
technique from a different branch of mathematics, or introducing a novel layer
of mathematical abstraction. This is as much true for informal mathematics as
for formal mathematics (e.g. in Lean).

2. Many contemporary AI models for theorem proving are based on pretrained large
   language models, and it is hard to determine the influence of solutions
   leaking into their training data.

As a consequence of these two points, it is hard to predict how benchmark scores
will translate into real-world performance in research mathematics. In fact:

3. Almost none of the AI systems that report state-of-the-art benchmark scores
   in academic papers are regularly used by mathematicians, even those that
   spend a lot of time writing formal mathematics in e.g. Lean.

Indeed, publishing a paper with a state-of-the-art score on some benchmark is
often the final goal of a research project. Even when the paper is accompanied
by source code and model weights, it is often challenging to install, run, and
to tweak into a system that the end user can fruitfully use in real world
situations. See also [3].

## Using sorry statements from public repositories

Nowadays, at any given moment there are dozens of teams of mathematicians working
on collaborative efforts to write formal mathematics in the Lean language. They
tend to host their work-in-progress in public repositories on GitHub. These
projects are typically littered with statements that have been formally stated,
but for which the implementation of a proof has been deferred. They are marked
by the `sorry` placeholder.

Such statements vary wildly in difficulty and type. They range from the main
target theorem of the project (e.g. the statement of Fermat's Last Theorem), to
useful intermediate statements, to lemmas that are mathematically obvious
(but require some work to treat formally), to statements that probably follow
easily from a lemma somewhere hidden in the `mathlib` library.



Compare with SWE-Bench [1], which aims to evaluate language models on real-world
software engineering tasks by using GitHub issues as a benchmark. See also
LeanAgent [2]

Advantages:

1. Sorry statements "in the wild" capture a wide range of different aspects of research mathematics.
2. Having a constant influx of *new* sorry statements mitigates the problem of data
   contamination.
3. Being able to fill a sorry in an ongoing formalization projection is almost
   by definition something that is useful to someone.


## The ecosystem

### The database

*SorryDB* is a continuously updating database of sorry statements in public lean repositories.
It reproduces these statements locally, and verifies that they compile
correctly, and that they represent mathematical statements to be proven and not
definitions to be filled (technically: that their parent type is `Prop`). It
stores all information needed to reproduce the statements.

It may be useful as a source of "real world" problems for training and testing
AI systems for theorem proving.

### The leaderboard server

The leaderboard server runs the live competition. It selects recent sorry
statements (that are still open) from the database, serves them to clients
(competitors) who attempt to prove them, and verifies the correctness of the
solutions returned by clients.



### Client

From the point of view of the client (or competitor), this should work as
follows:

The client polls the server for a new sorry statement, and reproduces the sorry
locally (by cloning and building the git repository). It attempts to prove the
statement (using a lean-interaction-tool of their choice) within the given time
limit. If successful the solution (a string of lean code replacing the `sorry`)
is uploaded back to the server.

To lower the barrier to entry, we intend to implement simple sample clients
using various lean interaction tools.

### Scoring

The classical "solved 27.3% of the benchmark" may not be the best way to report
the performance of systems. Indeed: problems will very wildly in level of
difficulty, and some will not admit a solution at all (e.g. the statement may
be incorrect). Moreover, competitors may join later, or might suffer from
downtime, making it unreasonable to expect all competitors to have
attempted the same statements.

Instead, we propose to score the *relative performance* of competitors. Whenever
some competitor succeeds in proving a statement that another failed to prove,
both their scores will be updated in an ELO-like manner.

## References

1. Jimenez, C. E., Yang, J., Wettig, A., Yao, S., Pei, K., Press, O., & Narasimhan, K. (2023). SWE-bench: Can Language Models Resolve Real-World GitHub Issues? arXiv:2310.06770. https://arxiv.org/abs/2310.06770

2. Kumarappan, A., Tiwari, M., Song, P., George, R. J., Xiao, C., & Anandkumar, A. (2024). LeanAgent: Lifelong Learning for Formal Theorem Proving. arXiv:2410.06209. https://arxiv.org/abs/2410.06209

3. Rute, J. (2025). The last mile [Video]. Lean Together 2025. https://www.youtube.com/watch?v=Yr8dzfVkeHg




