# pseudoscript for validating sorries, <var> refers to entries in new_sorries.json


## first prepare the repository
# clone into a directory named <head-sha>, and switch to <head-sha>

git clone --branch <branch> --single-branch https://github.com/<repository> <head-sha>
cd <head-sha>
git checkout <head-sha>

# try to build the lean code
lake exe cache get
lake build

## now prepare REPL
# lake translate-config lean (if lakefile.toml)
echo "require REPL from git \"https://github.com/leanprover-community/repl\"" >> lakefile.lean
lake update REPL

## now interact with REPL through json stdin/stdout to lake exe repl


# now for each sorry (better, for each file containing sorries)
# interact with repl through json

# navigate to the sorry by running
# { "cmd" : "import Mathlib.bla.bla" }
# { "cmd" : "import Mathlib.blabla" }
# ...
# { "cmd " : "lean code bla bla", "env" : 10}
# { "cmd" : "lean code bla bla", "env" : 11}
# ...
# { "cmd" : "lean code sorry bla", "env" : sorry_line - num_imports}

# now we should be able to obtain the pretty printed goal
# and importantly: the Type of the goal?

# ----


# the following is a command line call to get proofstates at sorries

echo '{"path": "<path>", "allTactics": true}' | lake exe repl > output.json

# output.json contains a dict key "sorries" with a list of the form
# "sorries":
#  [{"proofState": 0,
#    "pos": {"line": 24, "column": 2},
#    "goal":
#    "X Y Z : SSet\ny : Y _[0]\ng : Y ⟶ Z\n⊢ const y ≫ g = const (g.app (op [0]) y)",
#    "endPos": {"line": 24, "column": 7}},
#   {"proofState": 1,
#    "pos": {"line": 78, "column": 50},
#    "goal":
#    "X Y✝ : SSet\nA : X.Subcomplex\nB : Y✝.Subcomplex\nφ : Subpresheaf.toPresheaf A ⟶ Subpresheaf.toPresheaf B\nf g : A.RelativeMorphism B φ\nJ : Type u_1\ninst✝ : Category.{u_2, u_1} J\nY : SSet\n⊢ PreservesColimitsOfShape J (tensorRight Y)",
#    "endPos": {"line": 78, "column": 55}}],

# next we need to enter 