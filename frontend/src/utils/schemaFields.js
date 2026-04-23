/**
 * Converts Pydantic model_json_schema() output to the old output_fields/input_fields format
 * that the frontend expects (key, label, type, description, example, nullable, children).
 */

/**
 * Converts a JSON Schema property to the old field format used by the frontend.
 * Handles nested object properties by recursively converting them to `children`.
 * @param {string} key - Field key
 * @param {object} schema - JSON Schema property definition
 * @returns {object} Field object in old format
 */
function _schemaToField(key, schema) {
  const type = schema.type || 'any'
  // Prefer explicit title, then derive from key (snake_case → Title Case)
  const label = schema.title || key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  const description = schema.description || ''
  // Pydantic uses 'examples' as a list, 'default' as the default value
  const example = (schema.examples && schema.examples.length > 0)
    ? schema.examples[0]
    : (schema.default !== undefined ? schema.default : null)

  const field = {
    key,
    label,
    type,
    description,
    nullable: true,
    example,
  }

  // Handle nested object properties → convert to `children`
  if (schema.type === 'object' && schema.properties) {
    field.type = 'object'
    field.nullable = schema.required?.includes(key) ? false : true
    field.children = Object.entries(schema.properties).map(([childKey, childSchema]) =>
      _schemaToField(childKey, childSchema)
    )
  }

  return field
}

/**
 * Converts a Pydantic OutputModel JSON Schema to the old output_fields format.
 * @param {object} schema - Pydantic model_json_schema() result
 * @returns {Array} Flat array of field objects
 */
export function outputSchemaToFields(schema) {
  if (!schema || !schema.properties) return []
  return Object.entries(schema.properties).map(([key, propSchema]) =>
    _schemaToField(key, propSchema)
  )
}

/**
 * Converts a Pydantic InputModel JSON Schema to the old input_fields format.
 * @param {object} schema - Pydantic model_json_schema() result
 * @returns {Array} Flat array of field objects
 */
export function inputSchemaToFields(schema) {
  if (!schema || !schema.properties) return []
  const required = schema.required || []
  return Object.entries(schema.properties).map(([key, propSchema]) => {
    const type = propSchema.type || 'any'
    const label = propSchema.title || key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
    const description = propSchema.description || ''
    const example = (propSchema.examples && propSchema.examples.length > 0)
      ? propSchema.examples[0]
      : (propSchema.default !== undefined ? propSchema.default : null)
    return {
      key,
      label,
      type,
      description,
      required: required.includes(key),
      default: propSchema.default,
      options: propSchema.enum
        ? propSchema.enum.map(v => ({ label: String(v), value: v }))
        : [],
      source_field_type: '',
    }
  })
}
