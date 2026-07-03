import { cn } from '../../lib/utils.js';

export default function Label({ className, ...props }) {
  return (
    <label
      className={cn(
        'text-sm font-medium leading-none text-slate-800',
        'peer-disabled:cursor-not-allowed peer-disabled:opacity-70',
        className,
      )}
      {...props}
    />
  );
}