export default function SkeletonCard() {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 overflow-hidden shadow-sm animate-pulse flex flex-col h-full">
      <div className="aspect-square bg-gray-200"></div>
      <div className="p-4 flex flex-col flex-grow">
        <div className="h-6 bg-gray-200 rounded-md w-3/4 mb-4"></div>

        <div className="mt-auto pt-3">
          <div className="h-7 bg-gray-200 rounded-md w-1/2 mb-4"></div>
          <div className="h-11 bg-gray-200 rounded-xl w-full"></div>
        </div>
      </div>
    </div>
  )
}
