// Deck-wide switches. Edit here, or add ?cut=1 to the URL for the 3-minute cut.

/** Merge Scene 2 into Scene 1 and trim Scene 6 to 45 s (total about 2:51). */
export const CUT_TO_3MIN = false;

/** Running Clinic Assistant for a live iframe in Scene 6. Empty = play public/demo.mp4.
 *  Clinic Assistant v2.3 sends `frame-ancestors 'none'`, so it cannot be framed; leave this empty
 *  unless that header changes. */
export const CLINIC_ASSISTANT_URL = "";
