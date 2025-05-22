/**
 * Mapping of technician names to their Teams user IDs
 * This file can be updated to add more technicians as needed
 */

export interface UserMapping {
    name: string;
    teamsUserId: string;
}

// Default user ID to use if a specific mapping isn't found
export const DEFAULT_USER_ID = 'a1e82718-6bb0-40ee-b14e-d6fedc3bd575'; // Yolanda's user ID

// Map of technician names to their Teams user IDs
// For now, all technicians use Yolanda's user ID for testing
export const userMappings: Record<string, string> = {
    'Yolanda Cao': 'a1e82718-6bb0-40ee-b14e-d6fedc3bd575',
    'Michael Barbin': 'a1e82718-6bb0-40ee-b14e-d6fedc3bd575', // Using Yolanda's ID for testing
    'Jomaree Lawsin': 'a1e82718-6bb0-40ee-b14e-d6fedc3bd575', // Using Yolanda's ID for testing
    'Carl Tamayo': 'a1e82718-6bb0-40ee-b14e-d6fedc3bd575',    // Using Yolanda's ID for testing
    'Jorenzo Lucero': 'a1e82718-6bb0-40ee-b14e-d6fedc3bd575', // Using Yolanda's ID for testing
    'Carl Lim': 'a1e82718-6bb0-40ee-b14e-d6fedc3bd575',       // Using Yolanda's ID for testing
    'Needs human input': '',                                  // No user ID for this special case
};

/**
 * Get the Teams user ID for a given technician name
 * @param technicianName The name of the technician
 * @returns The Teams user ID for the technician, or the default ID if not found
 */
export function getTeamsUserId(technicianName: string): string {
    return userMappings[technicianName] || DEFAULT_USER_ID;
}
