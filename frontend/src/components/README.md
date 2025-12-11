# Modern UI Components

Beautiful, accessible React components for the Mamad Validation App.

## 🎨 Design Philosophy

- **Clean & Minimal** - Focus on content, not decoration
- **Consistent** - Reusable patterns across the app
- **Accessible** - WCAG AAA compliant, keyboard navigable
- **Delightful** - Smooth animations and micro-interactions

## 📦 Components

### Core UI (`src/components/ui/`)

#### Button
```tsx
import { Button } from './components/ui';

<Button variant="primary" size="md" icon={<Plus />} loading={false}>
  Click Me
</Button>
```

**Variants**: `primary`, `secondary`, `outline`, `ghost`, `danger`  
**Sizes**: `sm`, `md`, `lg`  
**Props**: `loading`, `icon`, `fullWidth`, `disabled`

---

#### Card
```tsx
<Card padding="lg" hover>
  <h3>Card Title</h3>
  <p>Card content...</p>
</Card>
```

**Padding**: `none`, `sm`, `md`, `lg`  
**Props**: `hover` (adds shadow on hover)

---

#### StatCard
```tsx
<StatCard 
  label="Total Items"
  value={150}
  icon={<FileText />}
  color="blue"
/>
```

**Colors**: `violet`, `green`, `blue`, `amber`, `red`, `gray`

---

#### Badge
```tsx
<Badge variant="success">Passed</Badge>
<Badge variant="error" size="md">Failed</Badge>
```

**Variants**: `success`, `error`, `warning`, `info`, `neutral`  
**Sizes**: `sm`, `md`

---

#### ProgressBar
```tsx
<ProgressBar 
  value={75} 
  max={100}
  color="violet"
  size="lg"
  showLabel
/>
```

**Colors**: `violet`, `green`, `blue`, `amber`  
**Sizes**: `sm`, `md`, `lg`

---

#### EmptyState
```tsx
<EmptyState
  icon={<Inbox />}
  title="No items found"
  description="Get started by creating your first item"
  action={{
    label: 'Create Item',
    onClick: handleCreate
  }}
/>
```

---

#### FloatingActionButton
```tsx
<FloatingActionButton
  onClick={handleClick}
  icon={<Plus />}
  label="New Item"
  position="bottom-right"
/>
```

**Positions**: `bottom-right`, `bottom-left`

---

### Validation Components

#### StepIndicator
```tsx
<StepIndicator 
  currentStep={2}
  steps={[
    { number: 1, title: 'Upload', description: 'Upload file' },
    { number: 2, title: 'Review', description: 'Review segments' },
    { number: 3, title: 'Validate', description: 'Run validation' },
  ]}
/>
```

---

#### FileUploadZone
```tsx
<FileUploadZone
  onFileSelect={(file) => console.log(file)}
  accept=".pdf,.png,.jpg"
  maxSize={50 * 1024 * 1024}
  loading={false}
/>
```

---

#### SegmentCard
```tsx
<SegmentCard
  segment={{
    segment_id: '001',
    title: 'Wall Section',
    description: 'Cross-section view',
    confidence: 0.85,
    thumbnail_url: '/path/to/image.png'
  }}
  onApprove={() => handleApprove('001')}
  onReject={() => handleReject('001')}
/>
```

---

## 🎨 Design System

### Colors
```typescript
import { colors } from './styles/design-system';

colors.primary[600]  // #8b5cf6
colors.success.DEFAULT  // #22c55e
colors.gray[900]  // #171717
```

### Spacing
```typescript
import { spacing } from './styles/design-system';

spacing.xs   // 4px
spacing.sm   // 8px
spacing.md   // 12px
spacing.lg   // 16px
spacing.xl   // 24px
spacing['2xl']  // 32px
```

### Shadows
```typescript
import { shadows } from './styles/design-system';

shadows.sm       // Subtle
shadows.DEFAULT  // Standard card
shadows.md       // Hover state
shadows.lg       // Modal/dropdown
```

---

## 🚀 Usage Example

```tsx
import { Button, Card, StatCard, ProgressBar } from './components/ui';
import { StepIndicator } from './components/ValidationComponents';

function MyPage() {
  return (
    <div className="min-h-screen bg-gray-50" dir="rtl">
      <main className="max-w-7xl mx-auto px-6 py-12">
        {/* Step Indicator */}
        <StepIndicator currentStep={2} steps={steps} />
        
        {/* Stats Grid */}
        <div className="grid grid-cols-3 gap-6 mb-8">
          <StatCard label="Total" value={150} color="blue" />
          <StatCard label="Success" value={120} color="green" />
          <StatCard label="Failed" value={30} color="red" />
        </div>
        
        {/* Main Content */}
        <Card padding="lg">
          <h2 className="text-2xl font-bold mb-4">Dashboard</h2>
          <ProgressBar value={80} max={100} showLabel />
          
          <div className="mt-6 flex gap-3">
            <Button variant="primary">Save</Button>
            <Button variant="secondary">Cancel</Button>
          </div>
        </Card>
      </main>
    </div>
  );
}
```

---

## ✨ Animations

All components include smooth transitions:

```css
transition: all 200ms cubic-bezier(0.4, 0, 0.2, 1)
```

Custom animations:
- `animate-fade-in` - Fade in with slide up
- `animate-slide-in` - Slide from side
- `animate-scale-in` - Scale from 95%

---

## 🌐 RTL Support

All components support RTL (Right-to-Left) for Hebrew:

```tsx
<div dir="rtl">
  {/* Components auto-adjust */}
</div>
```

---

## ♿ Accessibility

- **Focus rings** on all interactive elements
- **Keyboard navigation** fully supported
- **ARIA labels** where appropriate
- **High contrast** text (AAA compliant)
- **Semantic HTML** structure

---

## 📱 Responsive

All components are mobile-friendly and use Tailwind's responsive utilities:

```tsx
<div className="grid grid-cols-1 md:grid-cols-3">
  {/* Stacks on mobile, 3 columns on desktop */}
</div>
```

---

## 🛠️ Development

### Adding New Components

1. Create in `src/components/ui/index.tsx`
2. Follow existing patterns (variants, sizes, props)
3. Use design system tokens from `design-system.ts`
4. Add TypeScript types
5. Include hover/focus states
6. Test RTL mode

### Modifying Design System

Edit `src/styles/design-system.ts`:

```typescript
export const colors = {
  primary: {
    // Your colors
  }
};
```

---

## 📚 Documentation

Full documentation: `docs/ui-design-system.md`

---

## 🎯 Inspiration

- [Linear](https://linear.app) - Clean, professional interface
- [Vercel](https://vercel.com) - Modern, minimal design
- [Tailwind UI](https://tailwindui.com) - Component patterns

---

## 📄 License

Part of the Mamad Validation App project.
