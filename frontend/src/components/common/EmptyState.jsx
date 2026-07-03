export default function EmptyState({
  title = 'Nothing here yet',
  description = '',
  action = null,
  icon = null,
}) {
  return (
    <div className="flex flex-col items-center justify-center text-center px-6 py-12 border border-dashed border-slate-300 rounded-xl bg-white">
      <div className="h-12 w-12 rounded-full bg-slate-100 flex items-center justify-center text-slate-400 mb-4">
        {icon || (
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            className="h-6 w-6"
          >
            <path d="M4 6h16M4 12h10M4 18h6" strokeLinecap="round" />
          </svg>
        )}
      </div>
      <h3 className="text-base font-semibold text-slate-800">{title}</h3>
      {description && (
        <p className="mt-1 text-sm text-slate-500 max-w-sm">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}