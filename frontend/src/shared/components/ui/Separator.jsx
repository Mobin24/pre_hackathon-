import { cn } from '../../lib/utils.js';

export default function Separator({ className, orientation = 'horizontal' }) {
  return (
    <div
      role="separator"
      className={cn(
        'bg-slate-200',
        orientation === 'horizontal' ? 'h-px w-full' : 'w-px h-full',
        className,
      )}
    />
  );
}