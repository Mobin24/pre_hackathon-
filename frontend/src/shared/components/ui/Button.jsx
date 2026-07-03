import { cn } from '../../lib/utils.js';

const variants = {
  default:
    'bg-blue-600 text-white hover:bg-blue-700 active:bg-blue-800 shadow-sm',
  destructive:
    'bg-red-600 text-white hover:bg-red-700 active:bg-red-800 shadow-sm',
  outline:
    'border border-slate-200 bg-white text-slate-900 hover:bg-slate-50 active:bg-slate-100',
  secondary:
    'bg-slate-100 text-slate-900 hover:bg-slate-200 active:bg-slate-300',
  ghost: 'bg-transparent text-slate-900 hover:bg-slate-100',
  link: 'bg-transparent text-blue-600 underline-offset-4 hover:underline',
};

const sizes = {
  default: 'h-10 px-4 py-2 text-sm',
  sm: 'h-8 px-3 text-xs',
  lg: 'h-11 px-6 text-base',
  icon: 'h-10 w-10',
};

export default function Button({
  className,
  variant = 'default',
  size = 'default',
  asChild = false,
  ...props
}) {
  const base =
    'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md font-medium transition-colors focus-ring disabled:opacity-50 disabled:pointer-events-none';
  return (
    <button
      className={cn(base, variants[variant], sizes[size], className)}
      {...props}
    />
  );
}