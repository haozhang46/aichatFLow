# AGENTS.md

## Frontend conventions

- Shared primitive UI components go in `src/components/base`
- Business components go in `src/components/business`
- Layout components go in `src/components/layout`
- Route pages go in `src/pages` and must end with `Page`
- Hooks go in `src/hooks` and must start with `use`

## Naming

- React components: PascalCase
- Folders: PascalCase
- CSS blocks: kebab-case BEM
- Avoid `btn`, `wrp`, `cnt`, `box`, `item`

## Props

- booleans: `isXxx`, `hasXxx`, `canXxx`
- events: `onXxx`
- variants: `variant`, `size`, `status`

## Base components

Base components must be business-agnostic and reusable.
Do not place business-semantic components in `base`.

## Output behavior

When creating a component:
1. Identify the correct layer
2. Suggest the file path
3. Reuse existing components if possible
4. Keep implementation simple and consistent