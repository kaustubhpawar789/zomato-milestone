---
name: Culinary Compass Dark
colors:
  surface: '#131315'
  surface-dim: '#131315'
  surface-bright: '#39393b'
  surface-container-lowest: '#0e0e10'
  surface-container-low: '#1c1b1d'
  surface-container: '#201f22'
  surface-container-high: '#2a2a2c'
  surface-container-highest: '#353437'
  on-surface: '#e5e1e4'
  on-surface-variant: '#e4bebc'
  inverse-surface: '#e5e1e4'
  inverse-on-surface: '#313032'
  outline: '#ab8987'
  outline-variant: '#5b403f'
  surface-tint: '#ffb3b1'
  primary: '#ffb3b1'
  on-primary: '#680011'
  primary-container: '#ff535a'
  on-primary-container: '#5b000e'
  inverse-primary: '#bb162c'
  secondary: '#c6c6c7'
  on-secondary: '#2f3132'
  secondary-container: '#454748'
  on-secondary-container: '#b4b5b6'
  tertiary: '#c8c6c9'
  on-tertiary: '#303033'
  tertiary-container: '#919094'
  on-tertiary-container: '#29292c'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#ffdad8'
  primary-fixed-dim: '#ffb3b1'
  on-primary-fixed: '#410007'
  on-primary-fixed-variant: '#92001c'
  secondary-fixed: '#e2e2e3'
  secondary-fixed-dim: '#c6c6c7'
  on-secondary-fixed: '#1a1c1d'
  on-secondary-fixed-variant: '#454748'
  tertiary-fixed: '#e4e1e5'
  tertiary-fixed-dim: '#c8c6c9'
  on-tertiary-fixed: '#1b1b1e'
  on-tertiary-fixed-variant: '#47464a'
  background: '#131315'
  on-background: '#e5e1e4'
  surface-variant: '#353437'
typography:
  display-lg:
    fontFamily: Outfit
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  display-lg-mobile:
    fontFamily: Outfit
    fontSize: 36px
    fontWeight: '700'
    lineHeight: 42px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Outfit
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
  headline-lg-mobile:
    fontFamily: Outfit
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
  headline-md:
    fontFamily: Outfit
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  body-lg:
    fontFamily: Outfit
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Outfit
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  label-md:
    fontFamily: Outfit
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
    letterSpacing: 0.01em
  label-sm:
    fontFamily: Outfit
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.05em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 8px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  gutter: 16px
  margin-mobile: 16px
  margin-desktop: 64px
---

## Brand & Style

The design system is an immersive, high-energy interface designed for the modern foodie. It leverages a **Modern Corporate** style with **Glassmorphic** accents to create a premium, "night-out" atmosphere. The brand personality is adventurous, reliable, and vibrant.

By shifting to a dark aesthetic, the UI recedes to let food photography become the hero. The emotional response should be one of sophisticated discovery—evoking the feeling of a dimly lit, high-end bistro where the focus is entirely on the plate. Heavy use of depth through tonal layering and subtle translucency ensures the interface feels tactile yet digital-native.

## Colors

The palette is anchored by **Deep Charcoal (#09090B)** for the primary canvas, providing a rich, infinite background that eliminates glare. **Zomato Crimson (#E23744)** serves as the high-impact primary accent, used exclusively for critical actions, branding, and active states.

Secondary surfaces use **Slate Gray (#27272A)** to create container hierarchy. Text roles are strictly enforced for legibility:
- **Primary Text:** #F4F4F5 (Off-white for reduced eye strain)
- **Secondary Text:** #A1A1AA (Muted slate for metadata)
- **Accent Text:** #E23744 (Used sparingly for highlights)

Interactive elements in a "quiet" state utilize the tertiary Slate, while "loud" elements utilize the Crimson.

## Typography

The design system utilizes **Outfit** across all roles to maintain a geometric, clean, and modern appearance. The type scale is optimized for readability against dark backgrounds, employing slightly heavier weights for body copy to prevent "thinned" letterforms caused by light bleed on screens.

Headlines use tight tracking and bold weights to establish a clear information hierarchy. Labels and small captions use increased letter spacing to ensure clarity at small sizes.

## Layout & Spacing

This design system follows a **strict 8px grid (Rounded-Eight)**. All margins, paddings, and component heights must be multiples of 8px to ensure mathematical harmony across the UI.

- **Mobile:** 4-column fluid grid with 16px side margins.
- **Tablet:** 8-column fluid grid with 32px side margins.
- **Desktop:** 12-column fixed-max grid (1280px) centered, with 64px side margins.

Content blocks should use the `lg` (24px) spacing for internal padding to maintain a spacious, premium feel. Narrower gaps (`sm` or `md`) are reserved for grouping related metadata.

## Elevation & Depth

In this dark mode system, depth is communicated through **Tonal Layering** and **Subtle Glows** rather than traditional black shadows. 

1. **Surface Base:** #09090B (Background)
2. **Surface Level 1:** #18181B (Cards, navigation bars)
3. **Surface Level 2:** #27272A (Modals, floating action buttons)

For elevated elements like cards, apply a 1px solid border using #3F3F46 at 50% opacity to define edges against the dark background. Modals should utilize a **Backdrop Blur** (20px) to maintain context of the underlying content while emphasizing the foreground task. Use a very subtle Crimson outer glow (5% opacity) for high-priority active states.

## Shapes

The shape language is **Rounded**, reflecting the approachable and friendly nature of the brand.
- **Standard Components:** 0.5rem (8px) for buttons, input fields, and small cards.
- **Large Containers:** 1rem (16px) for main content cards and bottom sheets.
- **Interactive Pill:** Full rounding (999px) for chips, tags, and search bars to differentiate them from structural containers.

## Components

### Buttons
- **Primary:** Crimson background (#E23744), White text, 8px corner radius.
- **Secondary:** Slate background (#27272A), Off-white text.
- **Ghost:** No background, Crimson text, 1px Crimson border.

### Input Fields
Inputs should use the Level 1 surface (#18181B) with a 1px border (#3F3F46). On focus, the border transitions to Crimson (#E23744) with a subtle 4px outer glow.

### Cards
Cards use Level 1 surface layering. Images within cards should have a subtle dark gradient overlay at the bottom to ensure white text overlays remain legible.

### Chips & Tags
Use a pill shape. Active tags use a Crimson tint (Crimson at 15% opacity with Crimson text). Inactive tags use Level 2 surface (#27272A).

### Lists
List items are separated by subtle 1px lines (#18181B). Use 16px padding (md) to ensure touch targets are accessible and the UI feels airy.