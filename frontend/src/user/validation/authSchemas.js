import { z } from 'zod';

// Bangladesh mobile: 01XXXXXXXXX or +8801XXXXXXXXX
const BD_PHONE_REGEX = /^\+?8801[3-9]\d{8}$|^01[3-9]\d{8}$/;
// Bangladesh NID: 10 or 13 digits (legacy + smart card)
const BD_NID_REGEX = /^\d{10}$|^\d{13}$/;

const optionalBDPhone = z
  .string()
  .trim()
  .optional()
  .or(z.literal(''))
  .refine(
    (v) => !v || BD_PHONE_REGEX.test(v),
    'Enter a valid Bangladesh phone number (e.g. 01712345678 or +8801712345678).',
  );

const optionalBDNid = z
  .string()
  .trim()
  .optional()
  .or(z.literal(''))
  .refine(
    (v) => !v || BD_NID_REGEX.test(v),
    'NID must be 10 or 13 digits (Bangladesh national ID).',
  );

const optionalEmail = z
  .string()
  .trim()
  .optional()
  .or(z.literal(''))
  .refine(
    (v) => !v || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v),
    'Please enter a valid email address.',
  );

export const signupSchema = z
  .object({
    fullName: z.string().trim().min(1, 'Please enter your full name.'),
    nid: optionalBDNid,
    phone: optionalBDPhone,
    email: optionalEmail,
    password: z
      .string()
      .min(8, 'Password must be at least 8 characters.')
      .max(128, 'Password is too long.'),
    confirmPassword: z
      .string()
      .min(1, 'Please confirm your password.'),
  })
  .superRefine((data, ctx) => {
    if (data.password !== data.confirmPassword) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['confirmPassword'],
        message: 'Passwords do not match.',
      });
    }
    // At least one of email / phone / NID must be present so we can reach the user.
    if (!data.email && !data.phone && !data.nid) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['email'],
        message:
          'Please provide at least one contact method (email, phone, or NID).',
      });
    }
  });

export const signinSchema = z.object({
  identifier: z
    .string()
    .trim()
    .min(1, 'Please enter your email, phone, or NID.'),
  password: z.string().min(1, 'Please enter your password.'),
});

// Flatten Zod issues into a simple "first error" string, with an option to
// attach the field path so the UI can show field-level errors later.
export function formatZodError(error) {
  if (!error?.issues?.length) return 'Invalid input.';
  const issue = error.issues[0];
  return issue.message || 'Invalid input.';
}

export function fieldErrorsFromZod(error) {
  if (!error?.issues) return {};
  const map = {};
  for (const issue of error.issues) {
    const path = issue.path?.[0];
    if (path && !map[path]) map[path] = issue.message;
  }
  return map;
}