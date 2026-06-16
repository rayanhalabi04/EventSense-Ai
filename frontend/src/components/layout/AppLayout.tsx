import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'

export function AppLayout() {
  return (
    <div className="min-h-screen bg-bg-warm flex">
      <Sidebar />
      <main className="flex-1 ml-60 min-h-screen">
        <div className="max-w-[1280px] mx-auto px-6 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
