interface LogoProps {
  /** 'light' for light surfaces (navy mark), 'dark' for navy/dark surfaces (white mark). */
  variant?: 'light' | 'dark'
  className?: string
}

/**
 * EventSense brand mark — an "ES" monogram (navy "E" + champagne-gold "S")
 * with sparkle accents. Recolored from logo.svg to the design tokens.
 */
export function Logo({ variant = 'light', className = 'w-8 h-8' }: LogoProps) {
  const mark = variant === 'dark' ? '#FFFFFF' : '#172033'
  const accent = '#C8A96A'

  return (
    <svg
      viewBox="323 233 700 700"
      className={className}
      role="img"
      aria-label="EventSense"
      fill="none"
    >
      <g fill={accent}>
        <path d="M0,0 L33,0 L55,4 L65,7 L80,14 L92,21 L102,30 L109,41 L110,45 L110,58 L106,69 L100,77 L92,84 L90,84 L91,77 L91,55 L87,44 L79,33 L70,25 L57,17 L43,11 L27,8 L-2,8 L-18,12 L-33,20 L-43,28 L-50,39 L-54,49 L-55,53 L-55,68 L-51,84 L-45,94 L-36,104 L-26,112 L-11,121 L6,130 L35,143 L65,156 L94,170 L113,182 L124,191 L135,202 L145,216 L153,233 L157,249 L157,275 L154,291 L149,304 L141,319 L129,333 L117,343 L103,351 L89,357 L72,361 L61,363 L20,363 L-1,360 L-16,356 L-15,353 L-3,345 L6,346 L17,348 L29,349 L51,349 L76,344 L94,336 L104,329 L109,325 L119,312 L124,302 L127,294 L129,285 L129,263 L125,248 L118,235 L110,225 L101,216 L86,205 L65,193 L40,181 L10,168 L-16,156 L-31,148 L-45,138 L-55,129 L-65,116 L-72,102 L-76,87 L-76,66 L-73,54 L-65,38 L-56,27 L-46,18 L-32,10 L-18,4 Z" transform="translate(725,444)" />
        <path d="M0,0 L2,0 L7,22 L15,38 L24,47 L36,53 L48,56 L48,57 L36,60 L26,65 L16,74 L8,88 L4,100 L2,110 L0,110 L-4,92 L-12,76 L-20,67 L-28,62 L-40,58 L-46,57 L-43,55 L-32,52 L-22,47 L-17,43 L-9,32 L-3,18 L-1,10 Z" transform="translate(626,292)" />
        <path d="M0,0 L8,0 L13,3 L17,8 L17,65 L14,70 L11,73 L8,74 L0,74 L-6,69 L-8,66 L-8,8 L-2,1 Z" transform="translate(772,347)" />
        <path d="M0,0 L9,0 L14,3 L18,8 L18,65 L14,71 L9,74 L1,74 L-6,68 L-7,65 L-7,8 L-4,3 Z" transform="translate(469,347)" />
        <path d="M0,0 L2,0 L5,12 L12,23 L21,31 L28,34 L35,36 L35,39 L24,42 L18,46 L13,50 L6,61 L3,70 L2,76 L0,76 L-2,66 L-8,54 L-15,46 L-29,39 L-32,37 L-16,29 L-13,26 L-11,26 L-9,22 L-2,8 Z" transform="translate(935,663)" />
        <path d="M0,0 L10,0 L16,4 L20,10 L20,18 L15,26 L9,29 L2,29 L-5,25 L-8,20 L-8,8 L-3,2 Z" transform="translate(443,582)" />
        <path d="M0,0 L8,0 L14,4 L18,9 L19,11 L19,18 L14,26 L7,29 L0,29 L-6,25 L-9,19 L-9,9 L-2,1 Z" transform="translate(444,681)" />
      </g>
      <g fill={mark}>
        <path d="M0,0 L31,0 L31,16 L2,17 L-9,21 L-18,28 L-24,37 L-27,45 L-27,364 L-23,377 L-17,385 L-11,390 L-3,394 L3,396 L191,397 L192,398 L192,425 L191,441 L191,460 L198,453 L206,446 L219,435 L235,422 L254,408 L278,392 L300,379 L322,367 L340,357 L363,346 L369,343 L373,344 L374,348 L352,361 L329,375 L302,393 L280,408 L261,422 L247,433 L236,442 L222,454 L210,465 L200,474 L183,490 L177,495 L176,495 L176,478 L178,440 L179,412 L0,412 L-12,408 L-22,402 L-28,397 L-36,386 L-41,374 L-43,364 L-43,46 L-40,34 L-33,21 L-25,12 L-14,5 L-8,2 Z" transform="translate(419,379)" />
        <path d="M0,0 L197,0 L200,3 L199,10 L195,17 L17,17 L17,56 L12,62 L2,62 L-3,57 L-4,55 L-4,5 Z" transform="translate(441,477)" />
        <path d="M0,0 L27,0 L40,4 L51,11 L60,21 L66,33 L68,40 L68,231 L59,225 L54,221 L53,46 L50,36 L43,26 L34,20 L27,17 L0,16 Z" transform="translate(801,379)" />
        <path d="M0,0 L199,0 L204,5 L204,11 L199,16 L-1,16 L-5,12 L-5,5 Z" transform="translate(491,688)" />
        <path d="M0,0 L173,0 L185,11 L182,16 L0,16 L-5,11 L-5,5 Z" transform="translate(491,589)" />
        <path d="M0,0 L82,0 L88,3 L96,12 L97,16 L0,16 Z" transform="translate(498,379)" />
        <path d="M0,0 L77,0 L77,16 L-16,16 L-14,11 L-7,3 Z" transform="translate(676,379)" />
      </g>
    </svg>
  )
}
