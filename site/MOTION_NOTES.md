# Motion Notes

Observed in a desktop browser at 768px viewport height, from loaded scripts, DOM and computed styles while scrolling.

## Per site

- **landonorris.com** (loaded): Lenis; sticky scenes; a sticky horizontal track driven by `translateX`; split text; scroll-speed marquees; Rive canvases with scroll-trigger attributes.
- **danielneath.com** (loaded): Next.js; sticky section whose track moves `translateX` 1:1 across a 1,391px runway; skippable page reveal; reduced-motion CSS. No GSAP or Lenis global seen.
- **zrk.technology** (loaded): GSAP 3.15, ScrollTrigger (45 triggers, 2 scrubbed), Observer, Lenis; at least eight sticky scenes, tallest parent 8,448px; split text; custom cursor; two canvases; five videos.
- **drone.riotters.com** (loaded): Lenis global; Three.js r187 on a fixed canvas with Draco-compressed GLB models; Rive runtime; sticky panels with 2.9 to 3.6 viewport runways whose text spans change opacity.
- **jeskojets.com** (loaded): GSAP 3.13, ScrollTrigger (59 triggers, 23 scrubbed), SplitText, CustomEase, Lenis, Lottie; globe.gl and a Three.js r185 canvas; sticky scenes; hero layers scale and split apart on scroll.

Shared pattern: all five hold scenes with CSS `position: sticky`; no ScrollTrigger pin spacers appeared.

## Five best techniques for a technical product walkthrough

1. **Sticky scene with scrubbed timeline** (jeskojets, zrk)
   - Use: map each feature to one timeline across a long runway, so the frame holds whenever the presenter stops scrolling.
   - Reduced motion: unpin and show each scene's final state as stacked static content.
2. **Persistent stage with swapped layers** (drone.riotters, adapted to DOM layers)
   - Use: keep the product UI fixed while callouts and highlights change `opacity` at each scroll step.
   - Reduced motion: show the stage once with all callouts visible as a numbered list.
3. **Horizontal track inside a sticky scene** (landonorris, danielneath)
   - Use: `translateX` a detection-to-response flow through its stages, one stage per talking point.
   - Reduced motion: stack the stages vertically with no translation.
4. **Split-line text reveal** (jeskojets, zrk, landonorris)
   - Use: scrub lines in with `opacity` and `translateY`, giving each talking point its own scroll beat.
   - Reduced motion: render all text immediately at full opacity.
5. **Scale-and-split scene handoff** (jeskojets)
   - Use: scale the outgoing layer and part its halves with `translateX` to reveal the next feature.
   - Reduced motion: replace with an instant cut between scenes.

## Would not load

None.
