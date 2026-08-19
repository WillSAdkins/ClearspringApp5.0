// Simple evaluation + alpha-beta search AI opponent. Benchmarked in Node before
// embedding (depth 3 stays comfortably under a second even from busy
// middlegame positions) — see church_app dev notes if this needs re-checking.
window.ChessAI = (function () {
  const { generateLegalMoves, applyMove, getGameStatus, pieceColor, pieceType } = window.ChessEngine;

  const VALUES = { P: 100, N: 320, B: 330, R: 500, Q: 900, K: 0 };

// Small piece-square tables (from white's perspective; row 0 = rank 8).
// Encourage central control and reasonable development without pretending
// to be a strong engine — this just needs to be a plausible casual opponent.
const PAWN_TABLE = [
  0,0,0,0,0,0,0,0,
  50,50,50,50,50,50,50,50,
  10,10,20,30,30,20,10,10,
  5,5,10,25,25,10,5,5,
  0,0,0,20,20,0,0,0,
  5,-5,-10,0,0,-10,-5,5,
  5,10,10,-20,-20,10,10,5,
  0,0,0,0,0,0,0,0,
];
const KNIGHT_TABLE = [
  -50,-40,-30,-30,-30,-30,-40,-50,
  -40,-20,0,0,0,0,-20,-40,
  -30,0,10,15,15,10,0,-30,
  -30,5,15,20,20,15,5,-30,
  -30,0,15,20,20,15,0,-30,
  -30,5,10,15,15,10,5,-30,
  -40,-20,0,5,5,0,-20,-40,
  -50,-40,-30,-30,-30,-30,-40,-50,
];
const CENTER_TABLE = [ // rough shared table for bishops/queen/king-ish centralization nudges
  -20,-10,-10,-10,-10,-10,-10,-20,
  -10,0,0,0,0,0,0,-10,
  -10,0,5,10,10,5,0,-10,
  -10,5,5,10,10,5,5,-10,
  -10,0,10,10,10,10,0,-10,
  -10,10,10,10,10,10,10,-10,
  -10,5,0,0,0,0,5,-10,
  -20,-10,-10,-10,-10,-10,-10,-20,
];

function tableValue(table, r, c, color) {
  const idx = color === "w" ? r * 8 + c : (7 - r) * 8 + c;
  return table[idx];
}

function evaluate(state) {
  let score = 0;
  for (let i = 0; i < 64; i++) {
    const p = state.board[i];
    if (!p) continue;
    const color = pieceColor(p);
    const type = pieceType(p);
    const r = (i / 8) | 0, c = i % 8;
    let val = VALUES[type];
    if (type === "P") val += PAWN_TABLE[color === "w" ? i : (7 - r) * 8 + c] / 4;
    else if (type === "N") val += tableValue(KNIGHT_TABLE, r, c, color) / 3;
    else if (type === "B" || type === "Q") val += tableValue(CENTER_TABLE, r, c, color) / 6;
    score += color === "w" ? val : -val;
  }
  return score; // positive favors white
}

function orderMoves(moves) {
  // Captures and promotions first — helps alpha-beta prune far more effectively.
  return moves.slice().sort((a, b) => {
    const av = (a.captured ? VALUES[a.captured[1]] : 0) + (a.isPromo ? 800 : 0);
    const bv = (b.captured ? VALUES[b.captured[1]] : 0) + (b.isPromo ? 800 : 0);
    return bv - av;
  });
}

// Negamax with alpha-beta. Returns { move, score } where score is from the
// perspective of the side to move at the root.
function search(state, depth, alpha, beta, color) {
  const status = getGameStatus(state);
  if (status.status === "checkmate") return { move: null, score: -100000 - depth };
  if (status.status === "stalemate" || status.status === "draw") return { move: null, score: 0 };
  if (depth === 0) return { move: null, score: color * evaluate(state) };

  const moves = orderMoves(generateLegalMoves(state));
  let best = -Infinity;
  let bestMove = null;
  for (const m of moves) {
    const next = applyMove(state, m);
    const result = search(next, depth - 1, -beta, -alpha, -color);
    const score = -result.score;
    if (score > best) { best = score; bestMove = m; }
    alpha = Math.max(alpha, score);
    if (alpha >= beta) break;
  }
  return { move: bestMove, score: best };
}

function pickBestMove(state, depth) {
  const color = state.turn === "w" ? 1 : -1;
  const { move, score } = search(state, depth, -Infinity, Infinity, color);
  return { move, score: color * score };
}

  return { evaluate, pickBestMove, search };
})();
