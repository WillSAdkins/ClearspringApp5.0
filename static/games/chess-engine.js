// Chess engine core. Board is a 64-length array, index = rank*8 + file.
// rank 0 = the 8th rank (black's back rank, top of a white-orientation board),
// rank 7 = the 1st rank (white's back rank). file 0 = 'a' ... file 7 = 'h'.
// Pieces are two-char strings: color 'w'/'b' + type 'P','N','B','R','Q','K'.
//
// This file is unit-tested (including perft against known reference values for
// the starting position and several castling/en-passant/promotion "torture"
// positions) before being embedded here — see the church_app dev notes if this
// ever needs re-verifying after an edit.
window.ChessEngine = (function () {

function sq(r, c) { return r * 8 + c; }
function inBounds(r, c) { return r >= 0 && r < 8 && c >= 0 && c < 8; }

function createInitialState() {
  const board = new Array(64).fill(null);
  const back = ["R", "N", "B", "Q", "K", "B", "N", "R"];
  for (let c = 0; c < 8; c++) {
    board[sq(0, c)] = "b" + back[c];
    board[sq(1, c)] = "bP";
    board[sq(6, c)] = "wP";
    board[sq(7, c)] = "w" + back[c];
  }
  return {
    board,
    turn: "w",
    castling: { wK: true, wQ: true, bK: true, bQ: true },
    enPassant: null, // {r, c} of the square a pawn can capture into
    halfmoveClock: 0,
    fullmoveNumber: 1,
    history: [], // position keys, for threefold-ish bookkeeping (not required to be exhaustive)
  };
}

function cloneState(state) {
  return {
    board: state.board.slice(),
    turn: state.turn,
    castling: { ...state.castling },
    enPassant: state.enPassant ? { ...state.enPassant } : null,
    halfmoveClock: state.halfmoveClock,
    fullmoveNumber: state.fullmoveNumber,
    history: state.history.slice(),
  };
}

const KNIGHT_OFFSETS = [[-2,-1],[-2,1],[-1,-2],[-1,2],[1,-2],[1,2],[2,-1],[2,1]];
const KING_OFFSETS = [[-1,-1],[-1,0],[-1,1],[0,-1],[0,1],[1,-1],[1,0],[1,1]];
const BISHOP_DIRS = [[-1,-1],[-1,1],[1,-1],[1,1]];
const ROOK_DIRS = [[-1,0],[1,0],[0,-1],[0,1]];
const QUEEN_DIRS = BISHOP_DIRS.concat(ROOK_DIRS);

function opponent(color) { return color === "w" ? "b" : "w"; }

function pieceColor(p) { return p ? p[0] : null; }
function pieceType(p) { return p ? p[1] : null; }

// Is (r,c) attacked by any piece of `byColor`? Pure board query, ignores whose turn it is.
function isSquareAttacked(board, r, c, byColor) {
  // Pawns: a byColor pawn attacks (r,c) if it sits diagonally "behind" from that pawn's
  // perspective, i.e. attacker is one step further from its own promotion rank.
  const pawnDr = byColor === "w" ? 1 : -1; // white pawns attack upward (toward row 0), so the attacker is at r+1
  for (const dc of [-1, 1]) {
    const ar = r + pawnDr, ac = c + dc;
    if (inBounds(ar, ac)) {
      const p = board[sq(ar, ac)];
      if (p === byColor + "P") return true;
    }
  }
  for (const [dr, dc] of KNIGHT_OFFSETS) {
    const ar = r + dr, ac = c + dc;
    if (inBounds(ar, ac) && board[sq(ar, ac)] === byColor + "N") return true;
  }
  for (const [dr, dc] of KING_OFFSETS) {
    const ar = r + dr, ac = c + dc;
    if (inBounds(ar, ac) && board[sq(ar, ac)] === byColor + "K") return true;
  }
  for (const [dr, dc] of BISHOP_DIRS) {
    let ar = r + dr, ac = c + dc;
    while (inBounds(ar, ac)) {
      const p = board[sq(ar, ac)];
      if (p) {
        if (pieceColor(p) === byColor && (pieceType(p) === "B" || pieceType(p) === "Q")) return true;
        break;
      }
      ar += dr; ac += dc;
    }
  }
  for (const [dr, dc] of ROOK_DIRS) {
    let ar = r + dr, ac = c + dc;
    while (inBounds(ar, ac)) {
      const p = board[sq(ar, ac)];
      if (p) {
        if (pieceColor(p) === byColor && (pieceType(p) === "R" || pieceType(p) === "Q")) return true;
        break;
      }
      ar += dr; ac += dc;
    }
  }
  return false;
}

function findKing(board, color) {
  const target = color + "K";
  for (let i = 0; i < 64; i++) if (board[i] === target) return { r: (i / 8) | 0, c: i % 8 };
  return null;
}

function isInCheck(state, color) {
  const k = findKing(state.board, color);
  if (!k) return false;
  return isSquareAttacked(state.board, k.r, k.c, opponent(color));
}

// Generates pseudo-legal moves (does not yet filter out moves that leave own king in check).
function generatePseudoMoves(state) {
  const { board, turn } = state;
  const moves = [];
  const dir = turn === "w" ? -1 : 1; // white advances toward row 0
  const startRank = turn === "w" ? 6 : 1;
  const promoRank = turn === "w" ? 0 : 7;

  for (let r = 0; r < 8; r++) {
    for (let c = 0; c < 8; c++) {
      const p = board[sq(r, c)];
      if (!p || pieceColor(p) !== turn) continue;
      const type = pieceType(p);

      if (type === "P") {
        const one = r + dir;
        if (inBounds(one, c) && !board[sq(one, c)]) {
          addPawnMove(moves, r, c, one, c, promoRank, null);
          const two = r + 2 * dir;
          if (r === startRank && !board[sq(two, c)]) {
            moves.push({ from: {r,c}, to: {r: two, c}, piece: p, isDoublePawn: true });
          }
        }
        for (const dc of [-1, 1]) {
          const tr = r + dir, tc = c + dc;
          if (!inBounds(tr, tc)) continue;
          const target = board[sq(tr, tc)];
          if (target && pieceColor(target) !== turn) {
            addPawnMove(moves, r, c, tr, tc, promoRank, target);
          } else if (!target && state.enPassant && state.enPassant.r === tr && state.enPassant.c === tc) {
            moves.push({ from: {r,c}, to: {r: tr, c: tc}, piece: p, isEnPassant: true, captured: (turn==="w"?"bP":"wP") });
          }
        }
      } else if (type === "N") {
        for (const [dr, dc] of KNIGHT_OFFSETS) {
          const tr = r + dr, tc = c + dc;
          if (!inBounds(tr, tc)) continue;
          const target = board[sq(tr, tc)];
          if (!target || pieceColor(target) !== turn) {
            moves.push({ from: {r,c}, to: {r: tr, c: tc}, piece: p, captured: target || null });
          }
        }
      } else if (type === "K") {
        for (const [dr, dc] of KING_OFFSETS) {
          const tr = r + dr, tc = c + dc;
          if (!inBounds(tr, tc)) continue;
          const target = board[sq(tr, tc)];
          if (!target || pieceColor(target) !== turn) {
            moves.push({ from: {r,c}, to: {r: tr, c: tc}, piece: p, captured: target || null });
          }
        }
        addCastlingMoves(state, moves, r, c);
      } else {
        const dirs = type === "B" ? BISHOP_DIRS : type === "R" ? ROOK_DIRS : QUEEN_DIRS;
        for (const [dr, dc] of dirs) {
          let tr = r + dr, tc = c + dc;
          while (inBounds(tr, tc)) {
            const target = board[sq(tr, tc)];
            if (!target) {
              moves.push({ from: {r,c}, to: {r: tr, c: tc}, piece: p, captured: null });
            } else {
              if (pieceColor(target) !== turn) {
                moves.push({ from: {r,c}, to: {r: tr, c: tc}, piece: p, captured: target });
              }
              break;
            }
            tr += dr; tc += dc;
          }
        }
      }
    }
  }
  return moves;
}

function addPawnMove(moves, r, c, tr, tc, promoRank, captured) {
  if (tr === promoRank) {
    for (const promo of ["Q", "R", "B", "N"]) {
      moves.push({ from: {r,c}, to: {r: tr, c: tc}, promotion: promo, captured: captured || null, isPromo: true });
    }
  } else {
    moves.push({ from: {r,c}, to: {r: tr, c: tc}, captured: captured || null });
  }
}

function addCastlingMoves(state, moves, r, c) {
  const { board, turn, castling } = state;
  const opp = opponent(turn);
  if (isSquareAttacked(board, r, c, opp)) return; // can't castle out of check

  const rank = turn === "w" ? 7 : 0;
  if (r !== rank || c !== 4) return; // king not on its home square (already moved) — no castling

  const kSideRight = turn === "w" ? castling.wK : castling.bK;
  if (kSideRight && !board[sq(rank, 5)] && !board[sq(rank, 6)] && board[sq(rank,7)] === turn+"R") {
    if (!isSquareAttacked(board, rank, 5, opp) && !isSquareAttacked(board, rank, 6, opp)) {
      moves.push({ from: {r,c}, to: {r: rank, c: 6}, castle: "K" });
    }
  }
  const qSideRight = turn === "w" ? castling.wQ : castling.bQ;
  if (qSideRight && !board[sq(rank, 1)] && !board[sq(rank, 2)] && !board[sq(rank, 3)] && board[sq(rank,0)] === turn+"R") {
    if (!isSquareAttacked(board, rank, 3, opp) && !isSquareAttacked(board, rank, 2, opp)) {
      moves.push({ from: {r,c}, to: {r: rank, c: 2}, castle: "Q" });
    }
  }
}

// Applies a move (assumed legal or at least pseudo-legal) and returns a NEW state.
function applyMove(state, move) {
  const s = cloneState(state);
  const { board } = s;
  const turn = state.turn;
  const fromIdx = sq(move.from.r, move.from.c);
  const toIdx = sq(move.to.r, move.to.c);
  const piece = board[fromIdx];
  const type = pieceType(piece);

  s.enPassant = null;

  if (move.isEnPassant) {
    board[toIdx] = piece;
    board[fromIdx] = null;
    board[sq(move.from.r, move.to.c)] = null; // captured pawn sits beside the mover, same rank
  } else if (move.castle) {
    board[toIdx] = piece;
    board[fromIdx] = null;
    const rank = move.from.r;
    if (move.castle === "K") {
      board[sq(rank, 5)] = board[sq(rank, 7)];
      board[sq(rank, 7)] = null;
    } else {
      board[sq(rank, 3)] = board[sq(rank, 0)];
      board[sq(rank, 0)] = null;
    }
  } else {
    board[toIdx] = move.isPromo ? (turn + move.promotion) : piece;
    board[fromIdx] = null;
  }

  if (move.isDoublePawn) {
    s.enPassant = { r: (move.from.r + move.to.r) / 2, c: move.from.c };
  }

  // Castling-rights bookkeeping
  if (type === "K") {
    if (turn === "w") { s.castling.wK = false; s.castling.wQ = false; }
    else { s.castling.bK = false; s.castling.bQ = false; }
  }
  if (type === "R") {
    if (move.from.r === 7 && move.from.c === 0) s.castling.wQ = false;
    if (move.from.r === 7 && move.from.c === 7) s.castling.wK = false;
    if (move.from.r === 0 && move.from.c === 0) s.castling.bQ = false;
    if (move.from.r === 0 && move.from.c === 7) s.castling.bK = false;
  }
  // If a rook is captured on its home square, lose that castling right too.
  if (move.to.r === 7 && move.to.c === 0) s.castling.wQ = false;
  if (move.to.r === 7 && move.to.c === 7) s.castling.wK = false;
  if (move.to.r === 0 && move.to.c === 0) s.castling.bQ = false;
  if (move.to.r === 0 && move.to.c === 7) s.castling.bK = false;

  const wasCaptureOrPawn = type === "P" || !!move.captured || move.isEnPassant;
  s.halfmoveClock = wasCaptureOrPawn ? 0 : state.halfmoveClock + 1;
  if (turn === "b") s.fullmoveNumber += 1;
  s.turn = opponent(turn);
  return s;
}

function generateLegalMoves(state) {
  const pseudo = generatePseudoMoves(state);
  const legal = [];
  for (const m of pseudo) {
    const next = applyMove(state, m);
    if (!isInCheck(next, state.turn)) legal.push(m);
  }
  return legal;
}

function hasInsufficientMaterial(board) {
  const pieces = board.filter(Boolean);
  const nonKing = pieces.filter((p) => pieceType(p) !== "K");
  if (nonKing.length === 0) return true; // K vs K
  if (nonKing.length === 1 && (pieceType(nonKing[0]) === "N" || pieceType(nonKing[0]) === "B")) return true; // K+minor vs K
  if (nonKing.length === 2) {
    const types = nonKing.map(pieceType).sort().join("");
    if (types === "BB") {
      // K+B vs K+B is insufficient only if bishops are same-color-squared; good enough
      // approximation for a casual game — skip the exact square-color check.
    }
  }
  return false;
}

function getGameStatus(state) {
  const legal = generateLegalMoves(state);
  const inCheck = isInCheck(state, state.turn);
  if (legal.length === 0) {
    return inCheck ? { status: "checkmate", winner: opponent(state.turn) } : { status: "stalemate" };
  }
  if (state.halfmoveClock >= 100) return { status: "draw", reason: "50-move rule" };
  if (hasInsufficientMaterial(state.board)) return { status: "draw", reason: "insufficient material" };
  return { status: inCheck ? "check" : "ongoing" };
}

  return {
    sq, createInitialState, cloneState, generateLegalMoves, generatePseudoMoves,
    applyMove, isInCheck, getGameStatus, findKing, isSquareAttacked, pieceColor, pieceType,
  };
})();
