import "server-only";

import { createApiClient } from "@/lib/api-client";
import { getPublicEnv } from "@/lib/env";

export type Profile = {
  id: string;
  display_name: string | null;
  role: string;
  created_at: string;
};

export type SubjectDetail = {
  id: string;
  name: string;
  role: string;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
};

export type SubjectMember = {
  user_id: string;
  role: string;
  joined_at: string;
};

export async function fetchProfile(accessToken: string): Promise<Profile> {
  const client = createApiClient({ baseUrl: getPublicEnv().apiBaseUrl });
  return client.request<Profile>("/me", { token: accessToken });
}

export async function fetchSubject(accessToken: string, subjectId: string): Promise<SubjectDetail> {
  const client = createApiClient({ baseUrl: getPublicEnv().apiBaseUrl });
  return client.request<SubjectDetail>(`/subjects/${subjectId}`, { token: accessToken });
}

export async function fetchSubjectMembers(
  accessToken: string,
  subjectId: string
): Promise<SubjectMember[]> {
  const client = createApiClient({ baseUrl: getPublicEnv().apiBaseUrl });
  return client.request<SubjectMember[]>(`/subjects/${subjectId}/members`, { token: accessToken });
}
