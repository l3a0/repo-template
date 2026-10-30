// A DOM small enough to run the build board's script, plus a no-op setInterval
// so the page's stamp refresher does not keep the process alive.
//
// A parse check does not catch the defects the board actually ships. A comma
// dropped inside a nested array still parses, and a sentence that renders
// perfectly can still say something false. So the check is to execute the
// script and read what it produced. Two things run it on this stub: the
// harness in the l3a0 plugin's update-build-board skill, against a
// board.json built from GitHub, and
// tests/test_build_board.py, which holds what the page draws with no data, an
// empty board.json, a partial one and a fixture board.
//
// This is plain ES5 and assumes nothing about its host, so any JavaScript engine
// runs it. Where none is installed, `osascript -l JavaScript` is JavaScriptCore
// and is already present on macOS. Every element the script asks for is created on
// demand and kept in `store`, so a harness appended after the script can read
// `store.<id>.innerHTML` for any id the page renders into.
//
// Provenance: ported unchanged in code from
// .claude/skills/update-build-board/dom-stub.js in l3a0/quantitative-trading at
// commit 6da0ee3, landed here by the pull request that closes
// l3a0/repo-template#24. favicon.ico beside it came across unchanged too.
// The pull request that closes l3a0/repo-template#40 made `classList` keep
// its names, because the page sets the build order's four-column grid with a
// class, and a class nothing records is a layout no test can see. The pull
// request that closes l3a0/repo-template#45 gave each element a `value` and an
// `onchange`, so every element has the fields of the page's milestone
// selector. They are only defaults: the page sets both on the selector before
// anything reads them, and no test depends on them.
var store = {};
function mkClassList() {
  var names = [];
  function drop(n) { var i = names.indexOf(n); if (i >= 0) names.splice(i, 1); }
  return { names: names,
    add: function(){ for (var i = 0; i < arguments.length; i++) { drop(arguments[i]); names.push(arguments[i]); } },
    remove: function(){ for (var i = 0; i < arguments.length; i++) { drop(arguments[i]); } },
    toggle: function(n, force){
      var on = force === undefined ? names.indexOf(n) < 0 : !!force;
      drop(n); if (on) names.push(n); return on; } };
}
function mkEl(id) {
  return { id: id, innerHTML: "", textContent: "", value: "",
    classList: mkClassList(),
    querySelectorAll: function(){ return []; },
    onclick: null, onkeydown: null, onchange: null };
}
var document = {
  getElementById: function(id){ if(!store[id]) store[id]=mkEl(id); return store[id]; },
  addEventListener: function(){},
  // The board redraws on every changed board.json, and each redraw after the first
  // removes the Escape listener the previous one added. A stub without this
  // throws on the second render, which a page that drew only once never reached.
  removeEventListener: function(){} };
var setInterval = function(){ return 0; };
