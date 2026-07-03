export default function Spinner({ label = 'Loading…', size = 'md', className = '' }) {
  const sizes = { sm: 'h-4 w-4', md: 'h-6 w-6', lg: 'h-10 w-10' };
  return (
    <div role="status" className={`flex items-center gap-3 text-slate-500 ${className}`}>
      <span
        className={`${sizes[size]} rounded-full border-2 border-slate-300 border-t-blue-600 animate-spin`}
      />
      {label && <span className="text-sm">{label}</span>}
    </div>
  );
}