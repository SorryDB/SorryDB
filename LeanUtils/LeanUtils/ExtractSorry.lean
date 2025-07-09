import Lean

open Lean Elab Term Meta Syntax Command

structure SorryData (Out : Type) where
  out : Out
  stx : Syntax
  parentDecl : Name
deriving BEq

/-- Visit a node in the info tree and apply function `x` if the node
is a tactic info or term info. -/
def visitSorryNode {Out} (ctx : ContextInfo) (node : Info)
    (x : MVarId → MetaM (Option Out)) : IO (Option <| SorryData Out) := do
  match node with
  | .ofTacticInfo i =>
    match i.stx with
    | `(tactic| sorry) =>
      let some mvar := i.goalsBefore[0]? | return none
      let some mctx := (i.mctxBefore.decls.find? mvar) | return none
      match ← ctx.runMetaM mctx.lctx <| x mvar, ctx.parentDecl? with
      | some out, some name => return some ⟨out, i.stx, name⟩
      | _, _ => return none
    | _ => return none
  | .ofTermInfo i =>
    match i.stx with
    | `(term| sorry) => TermInfo.runMetaM i ctx do
      let some type := i.expectedType? | return none
      match ← x (← mkFreshExprMVar type).mvarId!, ctx.parentDecl? with
      | some out, some name => return some ⟨out, i.stx, name⟩
      | _, _ => return none
    | _ => return none
  | _ => return none

/-- Pretty print a goal if it doesn't contain any metavariables. -/
def ppGoalIfNoMVar (mvar : MVarId) : MetaM (Option Format) := do
  let e ← instantiateMVars <| ← mvar.getType
  unless !e.hasExprMVar do return none
  try
    return some <| ← ppGoal mvar
  catch _ =>
    return none

/-- Traverses an info tree and applies `x` on the type of each sorry,
while iteratively reconstructing the MetaM context.

Later, we apply this with `T = Option String`, where the output of `x`
is `none` if we cannot infer the type/pretty print the `Expr` corresponding
to a goal, or if the `Expr` contains some metavariables. -/
partial def traverseInfoTree {Out : Type}
    (x : MVarId → MetaM (Option Out)) (T : InfoTree) :
   IO (List <| SorryData Out) :=
  T.collectNodesBottomUpM go
where
  go (ctx : ContextInfo) (info : Info) (_ : PersistentArray InfoTree) (outs : List <| SorryData Out) :
    IO (List <| SorryData Out) := do
    let currentOuts := outs
    match ← visitSorryNode ctx info x with
    | some out => return currentOuts ++ [out]
    | none => return currentOuts

/-- Extract the sorries in an info tree that don't contain any metavariables. -/
def extractSorries (T : InfoTree) : IO (List <| SorryData Format) :=
  traverseInfoTree ppGoalIfNoMVar T

def extractInfoTrees (fileName : System.FilePath) : IO (FileMap × List InfoTree) := do

  let input ← IO.FS.readFile fileName
  let inputCtx := Parser.mkInputContext input fileName.toString
  let (header, parserState, messages) ← Parser.parseHeader inputCtx
  -- TODO: do we need to specify the main module here?
  let (env, messages) ← processHeader header {} messages inputCtx

  let commandState := Command.mkState env messages
  let s ← IO.processCommands inputCtx parserState commandState

  let fileMap := FileMap.ofString input

  return (fileMap, s.commandState.infoState.trees.toList)

-- A hack: the sorry extraction method currently seems to return duplicates
-- for some reason.
def List.Dedup {α : Type} [DecidableEq α] : List α → List α
  | [] => []
  | cons a l =>  if a ∈ l then l.Dedup else a :: l.Dedup

structure ParsedSorry where
  statement : String
  pos : Position
  parentDecl : Name
deriving ToJson, DecidableEq

def SorryData.toParsedSorry {Out} [ToString Out] (fileMap : FileMap) : SorryData Out → ParsedSorry :=
  fun ⟨out, stx, parentDecl⟩ => ⟨ToString.toString out, fileMap.toPosition stx.getPos?.get!, parentDecl⟩

instance : ToString ParsedSorry where
  toString a := ToString.toString <| ToJson.toJson a

def parseFile (path : System.FilePath) : IO (List ParsedSorry) := do
  let (fileMap, trees) ← extractInfoTrees path
  let sorryLists  ← trees.mapM extractSorries

  let sorryLists : List ParsedSorry := sorryLists.flatten.map (SorryData.toParsedSorry fileMap)
  let sorryLists := sorryLists.Dedup
  return sorryLists

def main (args : List String) : IO Unit := do
  if let some path := args[0]? then
    let path : System.FilePath := { toString := path }
    let out ← parseFile path
    let out : List Json := out.map ToJson.toJson
    IO.eprintln s!"File extraction yielded"
    IO.eprintln (toJson out)
  else
    IO.println "A path is needed."
