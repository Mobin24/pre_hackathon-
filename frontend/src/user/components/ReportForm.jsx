import { useRef, useState } from 'react';
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from '../../shared/components/ui/Card.jsx';
import Input from '../../shared/components/ui/Input.jsx';
import Textarea from '../../shared/components/ui/Textarea.jsx';
import Label from '../../shared/components/ui/Label.jsx';
import Button from '../../shared/components/ui/Button.jsx';
const BD_LOCATIONS = {
  Dhaka: {
    districts: ['Dhaka', 'Gazipur', 'Kishoreganj', 'Manikganj', 'Munshiganj', 'Narayanganj', 'Narsingdi', 'Tangail', 'Faridpur', 'Gopalganj', 'Madaripur', 'Rajbari', 'Shariatpur'],
  },
  Chittagong: {
    districts: ['Chittagong', 'Coxs Bazar', 'Comilla', 'Feni', 'Brahmanbaria', 'Chandpur', 'Lakshmipur', 'Noakhali', 'Khagrachhari', 'Rangamati', 'Bandarban'],
  },
  Rajshahi: {
    districts: ['Rajshahi', 'Bogura', 'Chapainawabganj', 'Joypurhat', 'Naogaon', 'Natore', 'Nawabganj', 'Pabna', 'Sirajganj'],
  },
  Khulna: {
    districts: ['Khulna', 'Bagerhat', 'Chuadanga', 'Jessore', 'Jhenaidah', 'Kushtia', 'Magura', 'Meherpur', 'Narail', 'Satkhira'],
  },
  Barisal: {
    districts: ['Barisal', 'Barguna', 'Bhola', 'Jhalokati', 'Patuakhali', 'Pirojpur'],
  },
  Sylhet: {
    districts: ['Sylhet', 'Habiganj', 'Moulvibazar', 'Sunamganj'],
  },
  Rangpur: {
    districts: ['Rangpur', 'Dinajpur', 'Gaibandha', 'Kurigram', 'Lalmonirhat', 'Nilphamari', 'Panchagarh', 'Thakurgaon'],
  },
  Mymensingh: {
    districts: ['Mymensingh', 'Jamalpur', 'Netrokona', 'Sherpur'],
  },
};
const DIVISION_NAMES = Object.keys(BD_LOCATIONS);
const getDistricts = (division) =>
  BD_LOCATIONS[division]?.districts || [];
const getUpazilas = () => [];

function LocationPicker({ value, onChange, gpsState, onUseGps }) {
  const districts = value.division ? getDistricts(value.division) : [];
  const upazilas =
    value.division && value.district
      ? getUpazilas(value.division, value.district)
      : [];

  function update(patch) {
    onChange({ ...value, ...patch });
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" variant="outline" onClick={onUseGps} disabled={gpsState.loading}>
          {gpsState.loading ? 'Locating…' : '📍 Use my current location'}
        </Button>
        {value.coords && (
          <span className="text-xs text-slate-600">
            GPS: {value.coords.lat.toFixed(5)}, {value.coords.lng.toFixed(5)}
          </span>
        )}
      </div>
      {gpsState.error && (
        <p className="text-sm text-red-600" role="alert">
          {gpsState.error}
        </p>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="division">Division</Label>
          <select
            id="division"
            value={value.division}
            onChange={(e) =>
              update({ division: e.target.value, district: '', upazila: '' })
            }
            className="flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            <option value="">Select division</option>
            {DIVISION_NAMES.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="district">District</Label>
          <select
            id="district"
            value={value.district}
            disabled={!value.division}
            onChange={(e) => update({ district: e.target.value, upazila: '' })}
            className="flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm disabled:bg-slate-50 disabled:text-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            <option value="">Select district</option>
            {districts.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="upazila">Upazila</Label>
          <select
            id="upazila"
            value={value.upazila}
            disabled={!value.district}
            onChange={(e) => update({ upazila: e.target.value })}
            className="flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm disabled:bg-slate-50 disabled:text-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            <option value="">Select upazila</option>
            {upazilas.map((u) => (
              <option key={u} value={u}>
                {u}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="area">Area / Landmark</Label>
        <Input
          id="area"
          placeholder="Village, neighborhood, or nearest landmark"
          value={value.area}
          onChange={(e) => update({ area: e.target.value })}
        />
      </div>
    </div>
  );
}

const ASSISTANCE_OPTIONS = [
  { key: 'rescue_team', label: 'Rescue Team', icon: '🚁' },
  { key: 'food', label: 'Food', icon: '🍞' },
  { key: 'water', label: 'Drinking Water', icon: '💧' },
  { key: 'medical', label: 'Medical Support', icon: '🩺' },
  { key: 'shelter', label: 'Shelter', icon: '🏠' },
  { key: 'medicine', label: 'Medicine', icon: '💊' },
  { key: 'ambulance', label: 'Ambulance', icon: '🚑' },
  { key: 'rescue_boat', label: 'Rescue Boat', icon: '🛶' },
  { key: 'baby_supplies', label: 'Baby Supplies', icon: '🍼' },
  { key: 'clothes', label: 'Clothes', icon: '👕' },
  { key: 'other', label: 'Other', icon: '✨' },
];

const TIME_OPTIONS = [
  { key: 'just_now', label: 'Just Now' },
  { key: 'within_1h', label: 'Within 1 Hour' },
  { key: 'today', label: 'Today' },
  { key: 'yesterday', label: 'Yesterday' },
  { key: 'older', label: 'More than one day ago' },
];

const MAX_IMAGES = 5;
const MAX_SIZE_MB = 6;

function ImageDropzone({ images, onChange, onError }) {
  const inputRef = useRef(null);
  const [isDragging, setIsDragging] = useState(false);

  function addFiles(fileList) {
    const incoming = Array.from(fileList || []);
    if (!incoming.length) return;
    const room = MAX_IMAGES - images.length;
    if (room <= 0) {
      onError(`You can attach up to ${MAX_IMAGES} images.`);
      return;
    }
    const accepted = [];
    let errored = false;
    for (const file of incoming) {
      if (accepted.length >= room) {
        onError(`You can attach up to ${MAX_IMAGES} images.`);
        errored = true;
        break;
      }
      if (!file.type.startsWith('image/')) {
        onError('Only image files are allowed.');
        errored = true;
        continue;
      }
      if (file.size > MAX_SIZE_MB * 1024 * 1024) {
        onError(`Each image must be under ${MAX_SIZE_MB}MB.`);
        errored = true;
        continue;
      }
      accepted.push({
        id: `img_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
        file,
        url: URL.createObjectURL(file),
        name: file.name,
      });
    }
    if (accepted.length) onChange([...images, ...accepted]);
    if (!errored) onError('');
  }

  function removeImage(id) {
    const target = images.find((i) => i.id === id);
    if (target?.url) URL.revokeObjectURL(target.url);
    onChange(images.filter((i) => i.id !== id));
  }

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          addFiles(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        className={`flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-8 text-center transition cursor-pointer focus:outline-none focus:ring-2 focus:ring-blue-500 ${
          isDragging
            ? 'border-blue-500 bg-blue-50'
            : 'border-slate-300 bg-slate-50 hover:bg-slate-100'
        }`}
      >
        <span className="text-3xl">📷</span>
        <p className="text-sm font-medium text-slate-800">
          Drag &amp; drop images here, or click to browse
        </p>
        <p className="text-xs text-slate-500">
          Up to {MAX_IMAGES} images · {MAX_SIZE_MB}MB each · JPG, PNG
        </p>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={(e) => {
            addFiles(e.target.files);
            e.target.value = '';
          }}
        />
      </div>

      {images.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
          {images.map((img) => (
            <div
              key={img.id}
              className="group relative aspect-square overflow-hidden rounded-md border border-slate-200 bg-slate-100"
            >
              <img
                src={img.url}
                alt={img.name}
                className="h-full w-full object-cover"
              />
              <button
                type="button"
                onClick={() => removeImage(img.id)}
                className="absolute top-1 right-1 rounded-full bg-white/90 text-slate-700 text-xs px-2 py-1 shadow-sm opacity-0 group-hover:opacity-100 transition"
                aria-label={`Remove ${img.name}`}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AssistanceChips({ selected, onToggle }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
      {ASSISTANCE_OPTIONS.map((opt) => {
        const active = selected.includes(opt.key);
        return (
          <button
            key={opt.key}
            type="button"
            onClick={() => onToggle(opt.key)}
            className={`flex items-center gap-3 rounded-lg border px-3 py-3 text-left text-sm transition shadow-sm ${
              active
                ? 'border-red-500 bg-red-50 text-red-900 ring-1 ring-red-200'
                : 'border-slate-200 bg-white text-slate-800 hover:border-slate-300 hover:bg-slate-50'
            }`}
            aria-pressed={active}
          >
            <span className="text-xl" aria-hidden>
              {opt.icon}
            </span>
            <span className="font-medium">{opt.label}</span>
            {active && (
              <span className="ml-auto text-red-600 font-bold" aria-hidden>
                ✓
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

function Radio({ name, value, checked, onChange, label, danger }) {
  return (
    <label
      className={`flex items-center gap-2 rounded-md border px-4 py-3 cursor-pointer transition ${
        checked
          ? danger
            ? 'border-red-500 bg-red-50 text-red-900 ring-1 ring-red-200'
            : 'border-blue-500 bg-blue-50 text-blue-900 ring-1 ring-blue-200'
          : 'border-slate-200 bg-white text-slate-800 hover:bg-slate-50'
      }`}
    >
      <input
        type="radio"
        name={name}
        value={value}
        checked={checked}
        onChange={onChange}
        className="sr-only"
      />
      <span
        className={`h-4 w-4 rounded-full border-2 ${
          checked
            ? danger
              ? 'border-red-500 bg-red-500'
              : 'border-blue-500 bg-blue-500'
            : 'border-slate-300'
        }`}
        aria-hidden
      />
      <span className="text-sm font-medium">{label}</span>
    </label>
  );
}

export default function ReportForm({ onSubmit }) {
  const [description, setDescription] = useState('');
  const [images, setImages] = useState([]);
  const [imageError, setImageError] = useState('');
  const [affectedCount, setAffectedCount] = useState('');
  const [assistance, setAssistance] = useState([]);
  const [immediateDanger, setImmediateDanger] = useState('');
  const [incidentTime, setIncidentTime] = useState('');
  const [notes, setNotes] = useState('');
  const [location, setLocation] = useState({
    division: '',
    district: '',
    upazila: '',
    area: '',
    coords: null,
  });
  const [gpsState, setGpsState] = useState({ loading: false, error: '' });

  function toggleAssistance(key) {
    setAssistance((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );
  }

  function handleUseGps() {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setGpsState({ loading: false, error: 'Geolocation is not supported in this browser.' });
      return;
    }
    setGpsState({ loading: true, error: '' });
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocation((prev) => ({
          ...prev,
          coords: { lat: pos.coords.latitude, lng: pos.coords.longitude },
        }));
        setGpsState({ loading: false, error: '' });
      },
      (err) => {
        setGpsState({
          loading: false,
          error:
            err?.message ||
            'Could not access your location. Please enter it manually below.',
        });
      },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }

  function handleSubmit(e) {
    e.preventDefault();
    const payload = {
      description: description.trim(),
      images: images.map(({ file, name }) => ({ name, size: file.size, type: file.type })),
      affectedCount: affectedCount ? Number(affectedCount) : null,
      assistance,
      immediateDanger: immediateDanger === 'yes',
      incidentTime,
      notes: notes.trim(),
      location,
      submittedAt: new Date().toISOString(),
    };
    onSubmit?.(payload);
  }

  const sectionCardClass =
    'border-slate-200 shadow-sm hover:shadow-md transition-shadow';

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* 1. Location */}
      <Card className={sectionCardClass}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <span className="text-xl" aria-hidden>📍</span>
            Current Location
          </CardTitle>
          <CardDescription>
            Share where the incident is happening so the right team can reach you.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <LocationPicker
            value={location}
            onChange={setLocation}
            gpsState={gpsState}
            onUseGps={handleUseGps}
          />
        </CardContent>
      </Card>

      {/* 2. Description */}
      <Card className={sectionCardClass}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <span className="text-xl" aria-hidden>📝</span>
            Incident Description
          </CardTitle>
          <CardDescription>
            Plain text works. The AI will structure it for the response team.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={6}
            placeholder="Describe what happened. Mention the current situation, affected people, and immediate needs."
            required
          />
        </CardContent>
      </Card>

      {/* 3. Upload Evidence */}
      <Card className={sectionCardClass}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <span className="text-xl" aria-hidden>🖼️</span>
            Upload Evidence
          </CardTitle>
          <CardDescription>
            Photos help responders understand the scale of the incident.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <ImageDropzone
            images={images}
            onChange={setImages}
            onError={setImageError}
          />
          {imageError && (
            <p className="text-sm text-red-600" role="alert">
              {imageError}
            </p>
          )}
        </CardContent>
      </Card>

      {/* 4. Affected people */}
      <Card className={sectionCardClass}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <span className="text-xl" aria-hidden>👥</span>
            Number of People Affected
          </CardTitle>
          <CardDescription>
            An estimate is fine — exact counts are not required.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2 max-w-xs">
            <Label htmlFor="affected" className="sr-only">
              Approximate number of people affected
            </Label>
            <Input
              id="affected"
              type="number"
              min="0"
              inputMode="numeric"
              placeholder="Approximate number"
              value={affectedCount}
              onChange={(e) => setAffectedCount(e.target.value)}
            />
          </div>
        </CardContent>
      </Card>

      {/* 5. Required Assistance */}
      <Card className={sectionCardClass}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <span className="text-xl" aria-hidden>🆘</span>
            Required Assistance
          </CardTitle>
          <CardDescription>
            Select all that apply — multiple options are allowed.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <AssistanceChips selected={assistance} onToggle={toggleAssistance} />
        </CardContent>
      </Card>

      {/* 6. Immediate danger */}
      <Card className={sectionCardClass}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <span className="text-xl" aria-hidden>⚠️</span>
            Immediate Danger
          </CardTitle>
          <CardDescription>
            Is there an active, ongoing risk to life right now?
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-md">
            <Radio
              name="danger"
              value="yes"
              checked={immediateDanger === 'yes'}
              onChange={() => setImmediateDanger('yes')}
              label="Yes — life at risk"
              danger
            />
            <Radio
              name="danger"
              value="no"
              checked={immediateDanger === 'no'}
              onChange={() => setImmediateDanger('no')}
              label="No — situation stable"
            />
          </div>
        </CardContent>
      </Card>

      {/* 7. Incident time */}
      <Card className={sectionCardClass}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <span className="text-xl" aria-hidden>⏱️</span>
            Incident Time
          </CardTitle>
          <CardDescription>
            Roughly when did the incident start?
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2 max-w-sm">
            <Label htmlFor="incident-time" className="sr-only">
              When did the incident happen?
            </Label>
            <select
              id="incident-time"
              value={incidentTime}
              onChange={(e) => setIncidentTime(e.target.value)}
              className="flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            >
              <option value="">Select timeframe</option>
              {TIME_OPTIONS.map((t) => (
                <option key={t.key} value={t.key}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>
        </CardContent>
      </Card>

      {/* 8. Additional notes */}
      <Card className={sectionCardClass}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <span className="text-xl" aria-hidden>📌</span>
            Additional Notes
          </CardTitle>
          <CardDescription>
            Anything else the response team should know? (optional)
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={4}
            placeholder="Contact details of a local coordinator, accessibility needs, hazards to watch for, etc."
          />
        </CardContent>
      </Card>

      {/* Submit */}
      <div className="sticky bottom-4 z-10">
        <Button
          type="submit"
          size="lg"
          className="w-full bg-red-600 hover:bg-red-700 text-white text-base sm:text-lg font-bold py-6 shadow-lg hover:shadow-xl"
        >
          🚨 Submit Emergency Report
        </Button>
        <p className="mt-2 text-center text-xs text-slate-500">
          Your report will be AI-structured and routed to verified responders
          in your area.
        </p>
      </div>
    </form>
  );
}