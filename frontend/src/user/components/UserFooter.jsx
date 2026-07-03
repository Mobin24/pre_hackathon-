export default function UserFooter() {
  return (
    <footer id="contact" className="bg-slate-900 text-slate-300">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-12 grid grid-cols-2 md:grid-cols-4 gap-8">
        <div className="col-span-2">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-blue-600 text-white font-bold">
              R
            </div>
            <span className="text-lg font-bold text-white">
              Relief<span className="text-blue-400">Grid</span>
            </span>
          </div>
          <p className="mt-3 text-sm text-slate-400 max-w-sm">
            AI-powered disaster response and relief coordination platform built
            for Bangladesh.
          </p>
        </div>
        <div>
          <h4 className="text-sm font-semibold text-white">Platform</h4>
          <ul className="mt-3 space-y-2 text-sm">
            <li><a href="#how-it-works" className="hover:text-white">How it works</a></li>
            <li><a href="#capabilities" className="hover:text-white">Capabilities</a></li>
            <li><a href="#incidents" className="hover:text-white">Live incidents</a></li>
          </ul>
        </div>
        <div>
          <h4 className="text-sm font-semibold text-white">Contact</h4>
          <ul className="mt-3 space-y-2 text-sm">
            <li>contact@reliefgrid.app</li>
            <li>+880 1700 000000</li>
          </ul>
        </div>
      </div>
      <div className="border-t border-slate-800">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-4 text-xs text-slate-500 flex flex-col sm:flex-row items-center justify-between gap-2">
          <p>© {new Date().getFullYear()} ReliefGrid. All rights reserved.</p>
          <p>Built for the Pre-Hackathon · Bangladesh</p>
        </div>
      </div>
    </footer>
  );
}