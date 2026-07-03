import { cn } from '../../lib/utils.js';

export default function Textarea({ className, ...props }) {
  return (
    <textarea
      className={cn(
        'flex min-h-[100px] w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm',
        'placeholder:text-slate-400',
        'focus-ring focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    />
  );
}